"""Tests for domain detection and the per-domain gates.

Detection is deterministic and precedence-ordered, so these pin both the answer
and the order. Each gate is tested against a fixture holding the specific
defect, so a passing suite means the gate discriminates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import domains  # noqa: E402

GOOD_README = "# thing\n\n" + ("Installs with pip. Then it does the job. " * 12)


def base(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(GOOD_README)
    (repo / "LICENSE").write_text("MIT License\n\n" + "Permission is hereby granted. " * 8)
    (repo / ".gitignore").write_text("__pycache__/\n")
    return repo


def codes(findings) -> set[str]:
    return {f.code for f in findings}


# --- detection ------------------------------------------------------------

def test_plain_repo_is_generic(tmp_path: Path):
    assert domains.detect(base(tmp_path)) == "generic"


def test_pyproject_is_a_python_library(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    assert domains.detect(repo) == "python-library"


def test_cargo_is_a_rust_crate(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "Cargo.toml").write_text('[package]\nname = "x"\n')
    assert domains.detect(repo) == "rust-crate"


def test_plugin_dir_wins_over_pyproject(tmp_path: Path):
    """Precedence matters. A plugin repo often also carries a language manifest."""
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / ".claude-plugin").mkdir()
    assert domains.detect(repo) == "claude-plugin"


def test_server_json_is_an_mcp_server(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "server.json").write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    assert domains.detect(repo) == "mcp-server"


def test_a_hand_written_jsonrpc_server_is_detected(tmp_path: Path):
    """An MCP server with no SDK dependency and no registry file. The method
    names are the only signal, and `initialize` plus `tools/call` is enough."""
    repo = base(tmp_path)
    src = repo / "src"
    src.mkdir()
    (src / "server.py").write_text(
        'def handle(method):\n'
        '    if method == "initialize":\n        return {}\n'
        '    if method == "tools/call":\n        return {}\n'
        '    return {"jsonrpc": "2.0"}\n'
    )
    assert domains.detect(repo) == "mcp-server"


def test_workspaces_field_is_a_monorepo(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "package.json").write_text(json.dumps({"name": "x", "workspaces": ["a"]}))
    assert domains.detect(repo) == "monorepo"


def test_mostly_markdown_is_docs(tmp_path: Path):
    repo = tmp_path / "docs"
    repo.mkdir()
    (repo / "README.md").write_text("# x\n")
    (repo / "guide.md").write_text("# guide\n")
    assert domains.detect(repo) == "docs"


# --- claude-plugin gate ---------------------------------------------------

def plugin_repo(tmp_path: Path, manifest: dict | None = None) -> Path:
    repo = base(tmp_path)
    holder = repo / ".claude-plugin"
    holder.mkdir()
    (holder / "plugin.json").write_text(json.dumps(
        manifest or {"name": "demo", "description": "does a thing"}))
    skill = repo / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\ndescription: does a thing\n---\n\n# Demo\n")
    return repo


def test_valid_plugin_passes(tmp_path: Path):
    found = domains.check_claude_plugin(plugin_repo(tmp_path))
    assert not [f for f in found if f.severity == "block"]


def test_plugin_manifest_without_description_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path, {"name": "demo"})
    assert "plugin-json-field" in codes(domains.check_claude_plugin(repo))


def test_invalid_plugin_json_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / ".claude-plugin" / "plugin.json").write_text("{not json")
    assert "plugin-json-invalid" in codes(domains.check_claude_plugin(repo))


def test_marketplace_entry_missing_source_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "m", "owner": {"name": "x"},
        "plugins": [{"name": "p", "description": "d"}],
    }))
    assert "marketplace-entry" in codes(domains.check_claude_plugin(repo))


def test_skill_without_frontmatter_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / "skills" / "demo" / "SKILL.md").write_text("# no frontmatter\n")
    assert "skill-frontmatter" in codes(domains.check_claude_plugin(repo))


def test_skill_missing_name_field_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / "skills" / "demo" / "SKILL.md").write_text(
        "---\ndescription: only a description\n---\n\n# Demo\n")
    assert "skill-field" in codes(domains.check_claude_plugin(repo))


def test_skill_name_mismatch_warns(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: other\ndescription: d\n---\n\n# Demo\n")
    found = domains.check_claude_plugin(repo)
    assert "skill-name-mismatch" in codes(found)
    assert not [f for f in found if f.code == "skill-name-mismatch" and f.severity == "block"]


def test_declared_path_that_does_not_exist_blocks(tmp_path: Path):
    """This plugin shipped `"commands": ["./commands/"]` with no such
    directory. Every field check passed, because the field was present and
    well-formed. Only the path itself was a lie."""
    repo = plugin_repo(tmp_path, {
        "name": "demo", "description": "d", "commands": ["./commands/"]})
    found = domains.check_claude_plugin(repo)
    assert "plugin-path-missing" in codes(found)
    assert any(f.code == "plugin-path-missing" and f.severity == "block" for f in found)


def test_declared_path_that_exists_passes(tmp_path: Path):
    repo = plugin_repo(tmp_path, {
        "name": "demo", "description": "d", "skills": ["./skills/demo"]})
    assert "plugin-path-missing" not in codes(domains.check_claude_plugin(repo))


def test_no_path_fields_is_normal(tmp_path: Path):
    """91 of 92 wshobson/agents manifests declare none. Absence is the norm,
    so it must never warn."""
    assert "plugin-path-missing" not in codes(
        domains.check_claude_plugin(plugin_repo(tmp_path)))


def test_invalid_hooks_json_blocks(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    (repo / "hooks").mkdir()
    (repo / "hooks" / "hooks.json").write_text("{broken")
    assert "hooks-json-invalid" in codes(domains.check_claude_plugin(repo))


# --- mcp gate -------------------------------------------------------------

def test_mcp_without_transport_in_readme_warns(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "server.json").write_text('{"name": "x"}')
    assert "mcp-transport-undocumented" in codes(domains.check_mcp_server(repo))


def test_mcp_with_transport_passes_that_check(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nRuns over stdio.\n")
    (repo / "server.json").write_text('{"name": "x"}')
    assert "mcp-transport-undocumented" not in codes(domains.check_mcp_server(repo))


def test_mcp_transport_prose_does_not_satisfy_the_check(tmp_path: Path):
    """`sse` matches inside "accessible". A README about OCR and accessibility
    passed this check while naming no transport at all."""
    repo = base(tmp_path)
    (repo / "README.md").write_text(
        GOOD_README + "\ntesseract ocr matches its accessible label")
    (repo / "server.json").write_text('{"name": "x"}')
    assert "mcp-transport-undocumented" in codes(domains.check_mcp_server(repo))


def test_mcp_without_registry_file_warns(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "README.md").write_text(GOOD_README + "\nRuns over stdio.\n")
    assert "mcp-registry-missing" in codes(domains.check_mcp_server(repo))


# --- language gates -------------------------------------------------------

def test_python_without_requires_python_warns(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    assert "python-no-requires" in codes(domains.check_python_library(repo))


def test_python_annotations_without_py_typed_warns(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n')
    (repo / "mod.py").write_text("def f(x: int) -> int:\n    return x\n")
    (repo / "tests").mkdir()
    assert "python-not-typed-marker" in codes(domains.check_python_library(repo))


def test_annotations_only_in_tests_need_no_py_typed(tmp_path: Path):
    """game-tune ships a script, and only its tests carry annotations."""
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n')
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def make() -> int:\n    return 1\n")
    assert "python-not-typed-marker" not in codes(domains.check_python_library(repo))


def test_rust_without_license_field_blocks(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "Cargo.toml").write_text('[package]\nname = "x"\n')
    assert "rust-no-license-field" in codes(domains.check_rust_crate(repo))


def test_rust_with_license_field_passes_that_check(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "Cargo.toml").write_text('[package]\nname = "x"\nlicense = "MIT"\n')
    (repo / "Cargo.lock").write_text("")
    (repo / "SECURITY.md").write_text("report\n")
    assert "rust-no-license-field" not in codes(domains.check_rust_crate(repo))


def test_npm_without_files_field_warns(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "package.json").write_text(json.dumps({"name": "x"}))
    found = codes(domains.check_node_library(repo))
    assert "npm-no-files-field" in found
    assert "npm-no-exports" in found
    assert "npm-no-engines" in found


def test_npm_with_publish_fields_passes(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "package.json").write_text(json.dumps({
        "name": "x", "files": ["dist"], "exports": {".": "./dist/x.js"},
        "engines": {"node": ">=22"},
    }))
    assert not codes(domains.check_node_library(repo)) & {
        "npm-no-files-field", "npm-no-exports", "npm-no-engines"}


# --- dispatch -------------------------------------------------------------

def test_check_domain_auto_detects_and_runs(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    resolved, found = domains.check_domain(repo, "auto")
    assert resolved == "claude-plugin"
    assert "claude-plugin-ok" in codes(found)


def test_check_domain_forced_overrides_detection(tmp_path: Path):
    repo = plugin_repo(tmp_path)
    resolved, _found = domains.check_domain(repo, "generic")
    assert resolved == "generic"


def test_unknown_domain_warns(tmp_path: Path):
    _resolved, found = domains.check_domain(base(tmp_path), "nonsense")
    assert "domain-unknown" in codes(found)


def test_list_domains_covers_every_gate():
    listed = {name for name, _marker in domains.list_domains()}
    assert listed == set(domains.DOMAIN_CHECKS)


# --- gates the checklist found untested -----------------------------------

def test_cli_without_entrypoint_or_usage_warns(tmp_path: Path):
    repo = base(tmp_path)
    found = codes(domains.check_cli_tool(repo))
    assert {"cli-no-entrypoint", "cli-no-usage"} <= found


def test_cli_with_script_and_usage_is_clean(tmp_path: Path):
    repo = base(tmp_path)
    (repo / "pyproject.toml").write_text('[project.scripts]\nthing = "thing:main"\n')
    (repo / "README.md").write_text(GOOD_README + "\n## Usage\n\n```\nthing run\n```\n")
    assert not codes(domains.check_cli_tool(repo)) & {"cli-no-entrypoint", "cli-no-usage"}


def test_monorepo_without_ci_warns(tmp_path: Path):
    assert "monorepo-no-ci" in codes(domains.check_monorepo(base(tmp_path)))


def test_monorepo_with_ci_is_clean(tmp_path: Path):
    repo = base(tmp_path)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    assert "monorepo-no-ci" not in codes(domains.check_monorepo(repo))


def test_docs_without_readme_blocks(tmp_path: Path):
    repo = tmp_path / "docs"
    repo.mkdir()
    assert "docs-no-index" in codes(domains.check_docs(repo))
    (repo / "README.md").write_text("# Docs\n")
    assert "docs-no-index" not in codes(domains.check_docs(repo))
