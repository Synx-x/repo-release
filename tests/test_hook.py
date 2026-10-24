"""Tests for the hook's trigger and version detection.

The hook is the only part of the plugin that runs without being asked, so its
triggers are pinned here rather than trusted to reading.
"""

from __future__ import annotations

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


def fire(tool: str, tool_input: dict, cwd: Path, env: dict | None = None) -> int:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "cwd": str(cwd),
        "tool_input": tool_input,
    }
    environment = {k: v for k, v in os.environ.items() if k != "REPO_RELEASE_MODE"}
    environment.update(env or {})
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), capture_output=True, text=True,
        env=environment, timeout=60,
    )
    return result.returncode


# --- publish triggers -----------------------------------------------------

def test_unready_publish_blocks(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    code = fire("Bash", {"command": "gh repo create x/y --public"}, bare)
    assert code == 2


def test_ready_publish_passes(tmp_path: Path):
    code = fire("Bash", {"command": "gh repo create x/y --public"}, ready_repo(tmp_path))
    assert code == 0


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
        "npm publish",
        "twine upload dist/*",
        "cargo publish",
    ):
        assert fire("Bash", {"command": command}, bare) == 2, command


def test_non_public_create_is_ignored(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "gh repo create x/y --private"}, bare) == 0


def test_publish_ok_escape_is_honoured(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert fire("Bash", {"command": "gh repo create x/y --public [publish-ok]"}, bare) == 0


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


def test_release_ok_escape_is_honoured(tmp_path: Path):
    repo = ready_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    code = fire("Edit", {
        "file_path": str(repo / "pyproject.toml"),
        "new_string": 'version = "0.2.0" [release-ok]',
        "old_string": 'version = "0.1.0"',
    }, repo)
    assert code == 0


def test_a_non_manifest_file_is_ignored(tmp_path: Path):
    repo = ready_repo(tmp_path)
    code = fire("Write", {"file_path": str(repo / "notes.md"), "content": "x"}, repo)
    assert code == 0
