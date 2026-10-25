#!/usr/bin/env python3
"""Block a publish or release until the validator and the checklist both pass.

Triggers:

  PreToolUse on Bash        a publish command: `gh repo create --public`,
                            `gh repo edit --visibility public`, `gh release create`,
                            a tag push, `gh api` creating a release, or a registry
                            upload (npm, pnpm, yarn, twine, uv, poetry, cargo)
  PreToolUse on Write|Edit  the version line in pyproject.toml, package.json,
                            Cargo.toml or plugin.json
  PreToolUse, any tool      an attempt to switch the gate off: editing the
                            installed plugin, the approvals, or a settings file
                            that sets REPO_RELEASE_MODE or disables the plugin
  UserPromptSubmit          the user typing [publish-ok], which approves one
                            publish in this session

A publish runs `scripts/validate.py` and `scripts/checklist.py`. The checklist
holds every line of every skill's `## Checklist`, so a step the agent skipped
fails the gate the same way a missing file does.

Only the user can grant an exception. The approval comes from the user's own
prompt, which the agent cannot write. [publish-ok] inside a tool call does
nothing. This closes the hole where an agent typed its own escape.

Mode, highest precedence first:

    REPO_RELEASE_MODE=off|warn|strict        environment
    hooks.repo_release.mode in the plugin config
    strict                                   default

Fail open. A crash inside this hook allows the call. A broken gate must never
strand the action it guards. A crashed check inside the checklist is a fail,
not a crash of the hook, so a broken check still blocks.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = PLUGIN_ROOT / "scripts" / "validate.py"
CHECKLIST = PLUGIN_ROOT / "scripts" / "checklist.py"
APPROVAL_TTL = 30 * 60
ESCAPE = "[publish-ok]"

# `git -C DIR push` is the same push as `git push`.
GIT_PUSH = r"\bgit(?:\s+-C\s+\S+)?\s+push\b"

# (pattern, profile). The profile names which checklist items apply.
PUBLISH_COMMANDS = (
    (re.compile(r"\bgh\s+repo\s+create\b[^\n|&;]*--public"), "public"),
    (re.compile(r"\bgh\s+repo\s+edit\b[^\n|&;]*--visibility[=\s]+public"), "public"),
    (re.compile(r"\bgh\s+release\s+create\b"), "release"),
    (re.compile(r"\bgh\s+release\s+edit\b[^\n|&;]*--draft[=\s]+false"), "release"),
    (re.compile(r"\bgh\s+api\b[^\n|&;]*/releases\b[^\n|&;]*(-X\s*POST|--method[=\s]+POST|"
                r"-f\s+tag_name|--field\s+tag_name)"), "release"),
    (re.compile(GIT_PUSH + r"[^\n|&;]*(--tags|--follow-tags|refs/tags/)"), "release"),
    (re.compile(GIT_PUSH + r"[^\n|&;]*\s[^\s-][^\s]*\s+v?\d+\.\d+\.\d+\S*"), "release"),
    (re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b"), "release"),
    (re.compile(r"\b(?:twine\s+upload|uv\s+publish|poetry\s+publish|flit\s+publish)\b"),
     "release"),
    (re.compile(r"\bcargo\s+publish\b"), "release"),
)

VERSION_FILES = ("pyproject.toml", "package.json", "Cargo.toml", "plugin.json")

# Paths and words that switch the gate off. The installed copy, never the source
# checkout, so developing this plugin stays possible.
INSTALLED = re.compile(r"\.claude/plugins/(?:cache|marketplaces)/repo-release\b")
DISABLE = re.compile(
    r"REPO_RELEASE_MODE|plugin\s+(?:disable|uninstall|remove)\s+repo-release|"
    r"\"repo-release@repo-release\"\s*:\s*false")
WRITE_VERB = re.compile(r"(?:^|[\s;&|])(?:sed\s+-i|tee|rm|mv|cp|truncate|chmod|ln|"
                        r"install|python3?\s+-c)\b|>>?")


def state_dir() -> Path:
    override = os.environ.get("REPO_RELEASE_STATE")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "repo-release"


def approval_path(session: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session or "unknown")
    return state_dir() / "approvals" / f"{safe}.json"


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


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


# --- user approval ----------------------------------------------------------

def on_prompt(payload: dict) -> None:
    """Record the user's [publish-ok]. The agent never writes a user prompt."""
    if ESCAPE not in str(payload.get("prompt") or ""):
        sys.exit(0)
    path = approval_path(str(payload.get("session_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": time.time()}))
    print("repo-release: [publish-ok] recorded; the next publish in this session "
          "skips the gate once")
    sys.exit(0)


def take_approval(session: str) -> bool:
    path = approval_path(session)
    try:
        record = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    path.unlink(missing_ok=True)
    return time.time() - float(record.get("at", 0)) < APPROVAL_TTL


# --- tamper guard -----------------------------------------------------------

def tamper(payload: dict) -> str:
    """Name the way a tool call would switch the gate off, or return ''."""
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    approvals = str(state_dir() / "approvals")
    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        if "repo-release/approvals" in command or approvals in command:
            return "the command touches the approval store, which only the user writes"
        if DISABLE.search(command) and re.search(r"plugin\s+(disable|uninstall|remove)|"
                                                 r"settings(\.local)?\.json", command):
            return "the command disables the repo-release gate"
        if INSTALLED.search(command) and WRITE_VERB.search(command):
            return "the command writes into the installed repo-release plugin"
        return ""
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if "repo-release/approvals" in path:
            return "the approval store is written only from the user's prompt"
        if INSTALLED.search(path):
            return "this edits the installed repo-release plugin, not its source"
        if Path(path).name in ("settings.json", "settings.local.json"):
            if DISABLE.search(json.dumps(tool_input)):
                return "this settings change switches the repo-release gate off"
    return ""


# --- publish ----------------------------------------------------------------

def segments(command: str) -> list[str]:
    return [s for s in re.split(r"&&|\|\||;|\n", command) if s.strip()]


def target_dir(command: str, cwd: Path) -> Path:
    """Follow `cd DIR` and `git -C DIR` to the directory the publish acts on."""
    here = cwd
    for part in segments(command):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        if len(words) >= 2 and words[0] == "cd":
            here = (here / Path(words[1]).expanduser()).resolve()
        if any(p.search(part) for p, _ in PUBLISH_COMMANDS):
            if "git" in words and "-C" in words:
                index = words.index("-C")
                if index + 1 < len(words):
                    return (here / Path(words[index + 1]).expanduser()).resolve()
            return here
    return here


def publish_profile(command: str) -> str:
    profiles = [profile for pattern, profile in PUBLISH_COMMANDS if pattern.search(command)]
    if not profiles:
        return ""
    return "release" if "release" in profiles else "public"


def run(script: Path, repo: Path, *args: str) -> tuple[int, str]:
    try:
        out = subprocess.run([sys.executable, str(script), str(repo), *args],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{script.name} did not finish: {exc}"
    return out.returncode, (out.stdout or "") + (out.stderr or "")


def gate(repo: Path, profile: str, expected: str = "", checklist: bool = True) -> tuple[bool, str]:
    args = ["--profile", profile, "--quiet", "--domain", "auto"]
    if expected:
        args += ["--version", expected]
    code, detail = run(VALIDATOR, repo, *args)
    report = f"validator ({profile}):\n{detail.strip()}"
    passed = code == 0
    if checklist:
        code, detail = run(CHECKLIST, repo, "--profile", profile)
        report += f"\n\nchecklist ({profile}):\n{detail.strip()}"
        passed = passed and code == 0
    return passed, report


def report(blocked: bool, detail: str) -> None:
    verdict = "blocked" if blocked else "warned"
    print(f"repo-release[{verdict}]\n{detail}", file=sys.stderr)
    if blocked:
        print("\nClose every open item, then publish again. An attest item needs "
              "`python3 <plugin>/scripts/checklist.py <repo> attest <id> --evidence ...` "
              "after you have done the check it names. Only the user can approve an "
              f"exception, by typing {ESCAPE} in a prompt.", file=sys.stderr)
    sys.exit(2 if blocked else 0)


def on_bash(payload: dict) -> None:
    command = str((payload.get("tool_input") or {}).get("command") or "")
    profile = publish_profile(command)
    if not profile:
        sys.exit(0)
    if take_approval(str(payload.get("session_id") or "")):
        print("repo-release: the user's [publish-ok] honoured for this call", file=sys.stderr)
        sys.exit(0)
    repo = target_dir(command, Path(payload.get("cwd") or os.getcwd()))
    passed, detail = gate(repo, profile)
    if passed:
        sys.exit(0)
    report(mode() == "strict", detail)


def on_write(payload: dict) -> None:
    tool_input = payload.get("tool_input") or {}
    path = str(tool_input.get("file_path") or "")
    if not path or Path(path).name not in VERSION_FILES:
        sys.exit(0)

    # Only a version change is interesting. A doc edit to the same file is not.
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
    if take_approval(str(payload.get("session_id") or "")):
        sys.exit(0)

    # The bump comes before the tag and the CI run, so only the validator applies.
    passed, detail = gate(Path(payload.get("cwd") or os.getcwd()), "release",
                          expected=new_version.group(1), checklist=False)
    if passed:
        sys.exit(0)
    report(mode() == "strict", detail)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    event = str(payload.get("hook_event_name") or "")
    try:
        if event == "UserPromptSubmit":
            on_prompt(payload)
        if event != "PreToolUse":
            return 0
        reason = tamper(payload)
        if reason:
            block(f"repo-release[blocked]: {reason}. Only the user can change the "
                  "gate, outside this session.")
        if mode() == "off":
            return 0
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
