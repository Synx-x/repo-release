#!/usr/bin/env python3
"""Block a publish or release that the validator would reject.

Two triggers:

  PreToolUse on Bash       `gh repo create --public`, `gh repo edit --visibility public`,
                           `git push --tags`, `npm publish`, `twine upload`, `cargo publish`
  PreToolUse on Write|Edit the version line in pyproject.toml / package.json / Cargo.toml

The first runs the public or release profile against the directory being
published. The second runs the release profile when a version changes, because
a bumped version with no changelog entry is a tag nobody can read.

Mode, highest precedence first:

    REPO_RELEASE_MODE=off|warn|strict        environment
    hooks.repo_release.mode in the plugin config
    strict                                   default

Strict is the default here, unlike the older warn-first guard, because the
validator exits 0 on a clean tree. A guard that only warns on a check that
already discriminates is a guard nobody reads.

Fail open. Any error inside this hook allows the call. A broken gate must never
strand the action it guards.

One-shot escape: put [publish-ok] in the command, or [release-ok] in the tool
input, to allow a single call. Both are logged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = PLUGIN_ROOT / "scripts" / "validate.py"

PUBLISH_COMMANDS = (
    re.compile(r"\bgh\s+repo\s+create\b[^\n|&;]*--public"),
    re.compile(r"\bgh\s+repo\s+edit\b[^\n|&;]*--visibility[=\s]+public"),
    re.compile(r"\bgit\s+push\b[^\n|&;]*--tags"),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b"),
    re.compile(r"\btwine\s+upload\b"),
    re.compile(r"\bcargo\s+publish\b"),
    re.compile(r"\bgh\s+release\s+create\b"),
)

VERSION_FILES = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "plugin.json",      # Claude Code plugin manifest, under .claude-plugin/
)


def mode() -> str:
    env = (os.environ.get("REPO_RELEASE_MODE") or "").strip().lower()
    if env in ("off", "warn", "strict"):
        return env
    cfg = {}
    for candidate in (
        Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "")) / "config.json",
        PLUGIN_ROOT / "config.json",
    ):
        try:
            cfg = json.loads(candidate.read_text())
            break
        except (OSError, json.JSONDecodeError):
            continue
    value = ""
    try:
        value = str(cfg.get("hooks", {}).get("repo_release", {}).get("mode", "")).lower()
    except AttributeError:
        value = ""
    if value in ("off", "warn", "strict"):
        return value
    return "strict"


def bash_command(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    return str(tool_input.get("command") or "")


def is_publish(command: str) -> bool:
    return any(pattern.search(command) for pattern in PUBLISH_COMMANDS)


def repo_dir(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.getcwd()
    return Path(cwd)


def validate(repo: Path, profile: str, expected: str = "") -> tuple[int, str]:
    command = [sys.executable, str(VALIDATOR), str(repo), "--profile", profile, "--quiet"]
    if expected:
        command += ["--version", expected]
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 0, f"validator did not run: {exc}"
    return out.returncode, (out.stdout or "") + (out.stderr or "")


def report(blocked: bool, profile: str, detail: str) -> None:
    verdict = "blocked" if blocked else "warned"
    print(f"repo-release[{verdict}]: profile {profile}\n{detail.strip()}", file=sys.stderr)
    if blocked:
        print(
            "\nFix the blocking findings, or add [publish-ok] to the command "
            "for a single deliberate exception.",
            file=sys.stderr,
        )
    sys.exit(2 if blocked else 0)


def on_bash(payload: dict) -> None:
    command = bash_command(payload)
    if not is_publish(command):
        sys.exit(0)
    if "[publish-ok]" in command:
        print("repo-release: [publish-ok] honoured for this call", file=sys.stderr)
        sys.exit(0)

    profile = "release" if "release" in command else "public"
    code, detail = validate(repo_dir(payload), profile)
    if code == 0:
        sys.exit(0)
    setting = mode()
    if setting == "off":
        sys.exit(0)
    report(setting == "strict", profile, detail)


def on_write(payload: dict) -> None:
    tool_input = payload.get("tool_input") or {}
    path = str(tool_input.get("file_path") or "")
    if not path or Path(path).name not in VERSION_FILES:
        sys.exit(0)
    blob = json.dumps(tool_input)
    if "[release-ok]" in blob:
        sys.exit(0)

    # Only a version change is interesting. A doc edit to the same file is not.
    # Two shapes to match: TOML `version = "x"` and JSON `"version": "x"`.
    new_text = str(tool_input.get("content") or tool_input.get("new_string") or "")
    old_text = str(tool_input.get("old_string") or "")
    version_line = re.compile(
        r'^[ \t]*["\']?version["\']?[ \t]*[=:][ \t]*["\']([^"\']+)["\']',
        re.MULTILINE,
    )
    new_version = version_line.search(new_text)
    old_version = version_line.search(old_text)
    if not new_version or (old_version and old_version.group(1) == new_version.group(1)):
        sys.exit(0)

    profile = "release"
    code, detail = validate(repo_dir(payload), profile, expected=new_version.group(1))
    if code == 0:
        sys.exit(0)
    setting = mode()
    if setting == "off":
        sys.exit(0)
    report(setting == "strict", profile, detail)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if mode() == "off":
        return 0
    event = str(payload.get("hook_event_name") or "")
    try:
        if event == "PreToolUse":
            tool = str(payload.get("tool_name") or "")
            if tool == "Bash":
                on_bash(payload)
            elif tool in ("Write", "Edit", "MultiEdit"):
                on_write(payload)
    except SystemExit:
        raise
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
