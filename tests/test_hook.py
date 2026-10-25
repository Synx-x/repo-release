"""Tests for the hook's trigger and version detection.

The hook is the only part of the plugin that runs without being asked, so its
triggers are pinned here rather than trusted to reading.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "guard_publish.py"

GOOD_README = "# thing\n\n" + ("Installs with pip. Then it does the job you named. " * 12)


def ready_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(GOOD_README)
    (repo / "LICENSE").write_text("MIT License\n\n" + "Permission is hereby granted. " * 8)
    (repo / ".gitignore").write_text("__pycache__/\n")
    (repo / "AGENTS.md").write_text("# Rules\n")
    return repo


def invoke(payload: dict, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    payload = {"session_id": "test-session", "cwd": str(cwd), **payload}
    environment = {k: v for k, v in os.environ.items() if not k.startswith("REPO_RELEASE_")}
    # Approvals land beside the fixture, never in the real state directory.
    environment["REPO_RELEASE_STATE"] = str(cwd.parent / "state")
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), capture_output=True, text=True,
        env=environment, timeout=120,
    )


def fire(tool: str, tool_input: dict, cwd: Path, env: dict | None = None) -> int:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    return invoke(payload, cwd, env).returncode


def approve(cwd: Path, prompt: str = "ship it [publish-ok]") -> None:
    invoke({"hook_event_name": "UserPromptSubmit", "prompt": prompt}, cwd)


def load_hook():
    spec = importlib.util.spec_from_file_location("guard_publish", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- publish triggers -----------------------------------------------------

def test_unready_publish_blocks(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    code = fire("Bash", {"command": "gh repo create x/y --public"}, bare)
    assert code == 2


def test_publish_passes_when_validator_and_checklist_pass(tmp_path: Path, monkeypatch):
    hook = load_hook()
    calls = []

    def fake_run(script, repo, *args):
        calls.append(script.name)
        return 0, ""

    monkeypatch.setattr(hook, "run", fake_run)
    passed, _ = hook.gate(ready_repo(tmp_path), "public")
    assert passed and calls == ["validate.py", "checklist.py"]


def test_checklist_blocks_when_the_validator_passes(tmp_path: Path):
    """A clean tree is not enough: the skipped steps still block."""
    result = invoke({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "gh repo create x/y --public"}},
                    ready_repo(tmp_path))
    assert result.returncode == 2
    assert "checklist (public)" in result.stderr and "BLOCKED" in result.stderr


def test_unrelated_command_is_ignored(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "ls -la"}, bare) == 0
    assert fire("Bash", {"command": "git status"}, bare) == 0


def test_every_publish_command_is_recognised(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    for command in (
        "gh repo create x/y --public",
        "gh repo edit --visibility public",
        "gh release create v1.0.0",
        "git push origin --tags",
        "git push --follow-tags",
        "git push origin v1.2.3",
        "git push origin refs/tags/v1.2.3",
        "gh release edit v1.0.0 --draft=false",
        "gh api repos/x/y/releases -X POST -f tag_name=v1",
        "npm publish",
        "twine upload dist/*",
        "uv publish",
        "cargo publish",
        "cd sub && gh release create v1.0.0",
        "git -C repo push --tags",
    ):
        assert fire("Bash", {"command": command}, bare) == 2, command


def test_non_public_create_is_ignored(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "gh repo create x/y --private"}, bare) == 0


def test_plain_push_is_not_a_publish(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "git push origin main"}, bare) == 0


def test_publish_ok_typed_by_the_agent_is_ignored(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "gh repo create x/y --public [publish-ok]"}, bare) == 2


def test_user_publish_ok_allows_exactly_one_publish(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    approve(bare)
    assert fire("Bash", {"command": "gh repo create x/y --public"}, bare) == 0
    assert fire("Bash", {"command": "gh repo create x/y --public"}, bare) == 2


def test_a_prompt_without_the_escape_approves_nothing(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    approve(bare, "please publish it")
    assert fire("Bash", {"command": "gh repo create x/y --public"}, bare) == 2


def test_cd_prefix_targets_the_named_directory(tmp_path: Path):
    hook = load_hook()
    target = hook.target_dir("cd sub && gh release create v1", tmp_path)
    assert target == (tmp_path / "sub").resolve()
    assert hook.target_dir("git -C repo push --tags", tmp_path) == (tmp_path / "repo").resolve()


# --- tamper guard ---------------------------------------------------------

INSTALLED = "/home/u/.claude/plugins/cache/repo-release/repo-release/0.4.0/hooks/"


def test_editing_the_installed_plugin_blocks(tmp_path: Path):
    path = INSTALLED + "hooks.json"
    assert fire("Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, tmp_path) == 2
    assert fire("Bash", {"command": f"sed -i s/strict/off/ {path}"}, tmp_path) == 2


def test_reading_the_installed_plugin_passes(tmp_path: Path):
    assert fire("Bash", {"command": f"cat {INSTALLED}hooks.json"}, tmp_path) == 0


def test_settings_that_switch_the_gate_off_block(tmp_path: Path):
    edit = {"file_path": "/home/u/.claude/settings.json",
            "old_string": "{", "new_string": '{"env": {"REPO_RELEASE_MODE": "off"},'}
    assert fire("Edit", edit, tmp_path) == 2
    assert fire("Bash", {"command": "claude plugin disable repo-release"}, tmp_path) == 2


def test_the_approval_store_is_off_limits(tmp_path: Path):
    command = "echo x > ~/.claude/state/repo-release/approvals/s.json"
    assert fire("Bash", {"command": command}, tmp_path) == 2


def test_mode_off_does_not_lift_the_tamper_guard(tmp_path: Path):
    edit = {"file_path": INSTALLED + "guard_publish.py", "old_string": "a", "new_string": "b"}
    assert fire("Edit", edit, tmp_path, {"REPO_RELEASE_MODE": "off"}) == 2


def test_mode_off_allows_everything(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    code = fire("Bash", {"command": "gh repo create x/y --public"}, bare,
                {"REPO_RELEASE_MODE": "off"})
    assert code == 0


def test_mode_warn_allows_everything(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    code = fire("Bash", {"command": "gh repo create x/y --public"}, bare,
                {"REPO_RELEASE_MODE": "warn"})
    assert code == 0


# --- version triggers -----------------------------------------------------

def test_toml_version_bump_without_changelog_blocks(tmp_path: Path):
    repo = ready_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (repo / "CHANGELOG.md").write_text("## 0.1.0\n")
    code = fire("Write", {
        "file_path": str(repo / "pyproject.toml"),
        "content": '[project]\nversion = "0.2.0"\n',
        "old_string": '[project]\nversion = "0.1.0"\n',
    }, repo)
    assert code == 2


def test_json_version_bump_without_changelog_blocks(tmp_path: Path):
    """The JSON shape carries a space before the colon. A TOML-only pattern
    silently misses it, and this plugin's own manifest is JSON."""
    repo = ready_repo(tmp_path)
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text('{\n  "version": "0.1.0"\n}')
    (repo / "CHANGELOG.md").write_text("## 0.1.0\n")
    code = fire("Write", {
        "file_path": str(manifest),
        "content": '{\n  "version": "0.2.0"\n}',
        "old_string": '{\n  "version": "0.1.0"\n}',
    }, repo)
    assert code == 2


def test_version_bump_with_changelog_entry_passes(tmp_path: Path):
    repo = ready_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (repo / "CHANGELOG.md").write_text("## 0.1.0\n")
    code = fire("Write", {
        "file_path": str(repo / "pyproject.toml"),
        "content": '[project]\nversion = "0.2.0"\n## 0.2.0\n',
        "old_string": '[project]\nversion = "0.1.0"\n',
    }, repo)
    # Changelog is not updated on disk yet, so the pending version is still
    # unreleased. Blocking here is correct behaviour, not a bug.
    assert code == 2


def test_edit_without_a_version_change_passes(tmp_path: Path):
    repo = ready_repo(tmp_path)
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text('{\n  "version": "0.1.0"\n}')
    code = fire("Edit", {
        "file_path": str(manifest),
        "new_string": '  "description": "x"',
        "old_string": '  "description": "y"',
    }, repo)
    assert code == 0


def test_user_approval_lets_one_version_edit_through(tmp_path: Path):
    repo = ready_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    edit = {
        "file_path": str(repo / "pyproject.toml"),
        "new_string": 'version = "0.2.0"',
        "old_string": 'version = "0.1.0"',
    }
    assert fire("Edit", edit, repo) == 2
    approve(repo)
    assert fire("Edit", edit, repo) == 0


def test_a_non_manifest_file_is_ignored(tmp_path: Path):
    repo = ready_repo(tmp_path)
    code = fire("Write", {"file_path": str(repo / "notes.md"), "content": "x"}, repo)
    assert code == 0
