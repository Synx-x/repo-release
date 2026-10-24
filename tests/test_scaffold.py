"""Tests for the scaffolder.

The property that matters is that it never overwrites: the usual case is
adding the missing pieces to a repo that already has a README worth keeping.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scaffold  # noqa: E402


def test_scaffold_writes_the_full_set(tmp_path: Path):
    code = scaffold.main([str(tmp_path), "--name", "thing", "--owner", "Synx-x"])
    assert code == 0
    for name in (
        "README.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "CHANGELOG.md",
        "CONTRIBUTING.md", "SECURITY.md", "LICENSE", ".env.example", ".gitignore",
    ):
        assert (tmp_path / name).exists(), name


def test_ci_lands_under_github_workflows(tmp_path: Path):
    scaffold.main([str(tmp_path)])
    assert (tmp_path / ".github" / "workflows" / "ci.yml").exists()
    assert not (tmp_path / "ci.yml").exists()


def test_agents_rules_and_workflows_are_copied(tmp_path: Path):
    scaffold.main([str(tmp_path)])
    assert (tmp_path / ".agents" / "rules" / "example-rule.md").exists()
    assert (tmp_path / ".agents" / "workflows" / "code-review.md").exists()


def test_existing_readme_is_kept(tmp_path: Path):
    original = "# mine\n\nHand written, and worth keeping.\n"
    (tmp_path / "README.md").write_text(original)
    scaffold.main([str(tmp_path), "--name", "thing"])
    assert (tmp_path / "README.md").read_text() == original


def test_existing_license_is_kept(tmp_path: Path):
    (tmp_path / "LICENSE").write_text("my own terms\n")
    scaffold.main([str(tmp_path), "--license", "Apache-2.0"])
    assert (tmp_path / "LICENSE").read_text() == "my own terms\n"


def test_name_is_substituted(tmp_path: Path):
    scaffold.main([str(tmp_path), "--name", "webbridge"])
    assert "<name>" not in (tmp_path / "README.md").read_text()


def test_apache_license_is_available(tmp_path: Path):
    scaffold.main([str(tmp_path), "--license", "Apache-2.0"])
    assert "Apache License" in (tmp_path / "LICENSE").read_text()


def test_unknown_license_is_usage_error(tmp_path: Path):
    assert scaffold.main([str(tmp_path), "--license", "WTFPL"]) == 2


def test_dry_run_writes_nothing(tmp_path: Path):
    scaffold.main([str(tmp_path), "--dry-run"])
    assert list(tmp_path.iterdir()) == []


def test_scaffolded_tree_has_no_placeholder_paths(tmp_path: Path):
    """The scaffold must not introduce a machine-local path of its own."""
    scaffold.main([str(tmp_path)])
    import validate

    found = validate.check_absolute_paths(tmp_path)
    assert not [f for f in found if f.severity == "block"]
