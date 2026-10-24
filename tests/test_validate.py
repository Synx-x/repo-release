"""Tests for the publish/release validator.

Each test builds a throwaway repo holding exactly the defect under test, so a
passing suite means the check discriminates rather than that the fixtures are
empty.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate  # noqa: E402

GOOD_README = "# thing\n\n" + ("Installs with pip. Then it does the job you named. " * 12)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(GOOD_README)
    (repo / "LICENSE").write_text("MIT License\n\n" + "Permission is hereby granted. " * 8)
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    return repo


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def check(repo: Path, name: str):
    return getattr(validate, name)(repo)


# --- env, plugin shape ----------------------------------------------------

def test_plugin_documents_vars_in_docs_instead_of_env_example(tmp_path: Path):
    """harness-kit reads 150 toggles and ships no .env.example. A toggle is
    behaviour, not setup, and nobody fills a .env for it."""
    repo = make_repo(tmp_path)
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "plugin.json").write_text('{"name":"x","description":"d"}')
    (repo / "mod.py").write_text('import os\nos.getenv("HK_TOGGLE_ONE")\n')
    (repo / "docs.md").write_text("Set HK_TOGGLE_ONE to change it.\n")
    found = check(repo, "check_env_example")
    assert "env-example-missing" not in codes(found)
    assert "env-ok" in codes(found)


def test_plugin_with_undocumented_vars_warns_not_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "plugin.json").write_text('{"name":"x","description":"d"}')
    (repo / "mod.py").write_text('import os\nos.getenv("HK_HIDDEN_TOGGLE")\n')
    found = check(repo, "check_env_example")
    assert "env-undocumented" in codes(found)
    assert not [f for f in found if f.severity == "block"]


def test_non_plugin_still_blocks_without_env_example(tmp_path: Path):
    """The relax applies to plugins only. A service still needs the file."""
    repo = make_repo(tmp_path)
    (repo / "app.py").write_text('import os\nos.getenv("DATABASE_URL")\n')
    assert "env-example-missing" in codes(check(repo, "check_env_example"))


# --- claimed counts -------------------------------------------------------

def test_stale_hook_count_warns(tmp_path: Path):
    """harness-kit claimed 72 hooks while holding 107 hook files."""
    repo = make_repo(tmp_path)
    (repo / "hooks").mkdir()
    for name in ("a", "b", "c"):
        (repo / "hooks" / f"{name}.py").write_text("")
    (repo / "README.md").write_text(
        "# x\n\n| | Count |\n|---|---|\n| Hooks | 72 |\n" + GOOD_README)
    found = check(repo, "check_claimed_counts")
    assert "claimed-count-stale" in codes(found)
    assert any("3" in f.message for f in found if f.code == "claimed-count-stale")


def test_accurate_hook_count_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "hooks").mkdir()
    for name in ("a", "b"):
        (repo / "hooks" / f"{name}.py").write_text("")
    (repo / "README.md").write_text(
        "# x\n\n| Hooks | 2 |\n" + GOOD_README)
    assert "claimed-count-stale" not in codes(check(repo, "check_claimed_counts"))


def test_no_countable_shape_is_not_accused(tmp_path: Path):
    """The check reads a table row only when the repo holds that shape."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("# x\n\n| Hooks | 72 |\n" + GOOD_README)
    assert "claimed-count-stale" not in codes(check(repo, "check_claimed_counts"))


# --- conformance ----------------------------------------------------------

def test_missing_security_route_warns(tmp_path: Path):
    repo = make_repo(tmp_path)
    assert "security-route-missing" in codes(check(repo, "check_conformance"))


def test_security_route_in_github_dir_passes(tmp_path: Path):
    """5 of 20 top repos keep it there, so both locations count."""
    repo = make_repo(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github" / "SECURITY.md").write_text("Report to security@example.com\n")
    assert "security-route-missing" not in codes(check(repo, "check_conformance"))


def test_no_ci_warns(tmp_path: Path):
    repo = make_repo(tmp_path)
    assert "ci-missing" in codes(check(repo, "check_conformance"))


def test_workflow_counts_as_ci(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    assert "ci-missing" not in codes(check(repo, "check_conformance"))


def test_renovate_counts_as_dependency_updates(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github" / "renovate.json5").write_text("{}\n")
    assert "dep-updates-unconfigured" not in codes(check(repo, "check_conformance"))


def test_conformance_never_blocks(tmp_path: Path):
    """A missing SECURITY.md is a gap, not a broken install. A gate that
    blocks on conventions half the top repos skip gets switched off."""
    found = check(make_repo(tmp_path), "check_conformance")
    assert not [f for f in found if f.severity == "block"]


# --- readme images --------------------------------------------------------

def test_local_image_that_is_missing_blocks(tmp_path: Path):
    """A 404 image is the most visible publish failure, and until 0.3.0
    nothing checked it."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\n![demo](docs/demo.png)\n")
    found = check(repo, "check_readme_images")
    assert "readme-image-missing" in codes(found)
    assert any(f.code == "readme-image-missing" and f.severity == "block"
               for f in found)


def test_local_image_that_exists_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "demo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (repo / "README.md").write_text(GOOD_README + "\n![demo](demo.png)\n")
    assert "readme-image-missing" not in codes(check(repo, "check_readme_images"))


def test_remote_image_is_not_fetched(tmp_path: Path):
    """The check stays offline. A hosted image may be fine and a network call
    in a publish gate is a new failure mode."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(
        GOOD_README + "\n![demo](https://example.com/x.png)\n")
    assert "readme-image-missing" not in codes(check(repo, "check_readme_images"))


# --- surface --------------------------------------------------------------

def test_complete_surface_passes(tmp_path: Path):
    found = check(make_repo(tmp_path), "check_surface")
    assert not [f for f in found if f.severity == "block"]


def test_missing_readme_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "README.md").unlink()
    assert "readme-missing" in codes(check(repo, "check_surface"))


def test_thin_readme_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("# thing\n")
    assert "readme-thin" in codes(check(repo, "check_surface"))


def test_missing_license_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "LICENSE").unlink()
    assert "license-missing" in codes(check(repo, "check_surface"))


def test_license_with_no_text_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "LICENSE").write_text("MIT\n")
    assert "license-thin" in codes(check(repo, "check_surface"))


# --- absolute paths -------------------------------------------------------

def test_absolute_home_path_in_readme_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nSee /home/alice/project/config.\n")
    assert "absolute-path" in codes(check(repo, "check_absolute_paths"))


def test_macos_and_mount_paths_block(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nOpen /Users/bob/x and /mnt/d/y.\n")
    found = [f for f in check(repo, "check_absolute_paths") if f.code == "absolute-path"]
    assert len(found) == 2


def test_tilde_path_is_portable_and_passes(tmp_path: Path):
    """A README saying config lives at ~/.app/config is correct, not a leak."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nConfig lives at ~/.webbridge/config.toml.\n")
    assert "absolute-path" not in codes(check(repo, "check_absolute_paths"))


def test_absolute_path_in_rule_file_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    rules = repo / ".agents" / "rules"
    rules.mkdir(parents=True)
    (rules / "style.md").write_text("Read /home/alice/notes.md first.\n")
    assert "absolute-path" in codes(check(repo, "check_absolute_paths"))


# --- secrets --------------------------------------------------------------

def test_github_token_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "notes.md").write_text("token: ghp_" + "a" * 36 + "\n")
    assert "secret" in codes(check(repo, "check_secrets"))


def test_anthropic_key_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "conf.py").write_text('KEY = "sk-ant-api03-' + "x" * 30 + '"\n')
    assert "secret" in codes(check(repo, "check_secrets"))


def test_private_key_block_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    banner = "-----BEGIN " + "OPENSSH PRIVATE KEY" + "-----"
    (repo / "id.txt").write_text(banner + "\nabc\n")
    assert "secret" in codes(check(repo, "check_secrets"))


def test_placeholder_token_passes(tmp_path: Path):
    """A documented placeholder must not block, or the gate gets switched off."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nSet OPENAI_API_KEY=sk-your-key-here\n")
    assert "secret" not in codes(check(repo, "check_secrets"))


def test_venv_is_not_scanned(tmp_path: Path):
    repo = make_repo(tmp_path)
    vendored = repo / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "leak.py").write_text("ghp_" + "b" * 36 + "\n")
    assert "secret" not in codes(check(repo, "check_secrets"))


# --- env example ----------------------------------------------------------

def test_getenv_is_detected(tmp_path: Path):
    """os.getenv is the common Python form. Missing it gives a false all-clear."""
    repo = make_repo(tmp_path)
    (repo / "app.py").write_text('import os\nx = os.getenv("APP_TOKEN")\n')
    assert "env-example-missing" in codes(check(repo, "check_env_example"))


def test_documented_variable_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "app.py").write_text('import os\nx = os.environ.get("APP_TOKEN")\n')
    (repo / ".env.example").write_text("APP_TOKEN=\n")
    assert "env-undocumented" not in codes(check(repo, "check_env_example"))


def test_undocumented_variable_warns(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "app.py").write_text('import os\nx = os.environ.get("APP_TOKEN")\n')
    (repo / ".env.example").write_text("OTHER=\n")
    assert "env-undocumented" in codes(check(repo, "check_env_example"))


# --- agent-native ---------------------------------------------------------

def test_missing_agents_md_warns_not_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    found = check(repo, "check_agents_md")
    assert "agents-md-missing" in codes(found)
    assert not [f for f in found if f.severity == "block"]


def test_bridge_without_import_warns(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# Rules\n")
    (repo / "CLAUDE.md").write_text("# Claude\n\nWrite tests first.\n")
    assert "bridge-diverges" in codes(check(repo, "check_agents_md"))


def test_thin_bridge_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# Rules\n")
    (repo / "CLAUDE.md").write_text("@AGENTS.md\n")
    assert "bridge-diverges" not in codes(check(repo, "check_agents_md"))
    assert "bridge-long" not in codes(check(repo, "check_agents_md"))


def test_cited_path_that_moved_warns(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "AGENTS.md").write_text("Config lives in `src/old/config.py`.\n")
    assert "cited-path-missing" in codes(check(repo, "check_cited_paths"))


def test_cited_path_that_exists_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "config.py").write_text("x = 1\n")
    (repo / "AGENTS.md").write_text("Config lives in `src/config.py`.\n")
    assert "cited-path-missing" not in codes(check(repo, "check_cited_paths"))


# --- release --------------------------------------------------------------

def test_release_needs_a_changelog(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.0"\n')
    assert "changelog-missing" in codes(check(repo, "check_release"))


def test_changelog_must_name_the_version(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.0"\n')
    (repo / "CHANGELOG.md").write_text("## 1.1.0\n\n- old\n")
    assert "changelog-stale" in codes(check(repo, "check_release"))


def test_release_complete_passes(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.0"\n')
    (repo / "CHANGELOG.md").write_text("## 1.2.0\n\n- ship\n")
    found = check(repo, "check_release")
    assert not [f for f in found if f.severity == "block"]


def test_placeholder_version_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "package.json").write_text(json.dumps({"name": "x", "version": "0.0.0"}))
    (repo / "CHANGELOG.md").write_text("## 0.0.0\n")
    assert "version-placeholder" in codes(check(repo, "check_release"))


def test_pending_version_is_checked_instead_of_the_one_on_disk(tmp_path: Path):
    """The check judges a bump against the version being written. Reading the
    file on disk judges it against the release it replaces, so a bump always
    passes."""
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    (repo / "CHANGELOG.md").write_text("## 0.1.0\n")
    assert "changelog-stale" not in codes(check(repo, "check_release"))
    pending = validate.check_release(repo, expected="0.2.0")
    assert "changelog-stale" in codes(pending)


def test_plugin_manifest_counts_as_a_version_source(tmp_path: Path):
    repo = make_repo(tmp_path)
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"name": "p", "version": "1.0.0"}))
    (repo / "CHANGELOG.md").write_text("## 1.0.0\n")
    found = codes(validate.check_release(repo))
    assert "version-missing" not in found
    assert "changelog-stale" not in found


# --- hygiene --------------------------------------------------------------

def test_missing_gitignore_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").unlink()
    assert "gitignore-missing" in codes(check(repo, "check_hygiene"))


def test_tracked_venv_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".venv").mkdir()
    (repo / ".venv" / "x").write_text("y")
    (repo / ".gitignore").write_text(".venv/\n")
    subprocess.run(["git", "add", "-f", ".venv/x"], cwd=repo, check=True)
    assert "vendored-deps" in codes(check(repo, "check_hygiene"))


# --- runner ---------------------------------------------------------------

def test_cli_exits_one_on_blocking(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "LICENSE").unlink()
    assert validate.main([str(repo), "--profile", "public", "--quiet"]) == 1


def test_cli_json_reports_readiness(tmp_path: Path):
    repo = make_repo(tmp_path)
    code = validate.main([str(repo), "--json"])
    assert code in (0, 1)


def test_missing_directory_is_usage_error(tmp_path: Path):
    assert validate.main([str(tmp_path / "nope")]) == 2
