"""Warnings name conventions, and conventions hold on every repo.

A warning blocks in every profile unless `validate.KEEP_WARN` names a reason it
cannot. Rules that guess block only at release. A pending version bump keeps
its dirty tree and missing tag as warnings, because neither can hold yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import domains  # noqa: E402
import validate  # noqa: E402

README = "# thing\n\n" + ("Installs with pip. Then it does the job you named. " * 12)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(README)
    (repo / "LICENSE").write_text("MIT License\n\n" + "Permission is hereby granted. " * 8)
    (repo / ".gitignore").write_text("__pycache__/\n")
    return repo


def severities(findings) -> dict[str, str]:
    return {f.code: f.severity for f in findings}


def warn(code: str) -> validate.Finding:
    return validate.Finding("warn", code, "message")


@pytest.mark.parametrize("profile", ["public", "release"])
def test_conventions_block_in_every_profile(tmp_path: Path, profile: str):
    found = severities(validate.run(make_repo(tmp_path), profile))
    for code in ("security-route-missing", "contributing-missing", "ci-missing",
                 "gitattributes-missing", "agents-md-missing"):
        assert found[code] == "block", code


def test_domain_conventions_block(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.0.0"\n')
    _, extra = domains.check_domain(repo, "auto")
    found = severities(validate.escalate(extra, "public", pending=False))
    assert found["python-no-tests"] == "block"


@pytest.mark.parametrize("code", sorted(validate.KEEP_WARN))
def test_listed_reasons_stay_warnings(code: str):
    for profile in ("public", "release"):
        assert validate.escalate([warn(code)], profile, pending=False)[0].severity == "warn"


@pytest.mark.parametrize("code", sorted(validate.RELEASE_REQUIRED))
def test_guessing_rules_block_only_at_release(code: str):
    assert validate.escalate([warn(code)], "public", pending=False)[0].severity == "warn"
    assert validate.escalate([warn(code)], "release", pending=False)[0].severity == "block"


def test_pending_bump_keeps_dirty_tree_and_tag_as_warnings():
    found = severities(validate.escalate(
        [warn("dirty-tree"), warn("tag-missing"), warn("contributing-missing")],
        "release", pending=True))
    assert found == {"dirty-tree": "warn", "tag-missing": "warn", "contributing-missing": "block"}


def test_pre_tag_keeps_only_the_tag_as_a_warning():
    """CI checks a committed version before its tag exists. The tree must be clean."""
    found = severities(validate.escalate(
        [warn("tag-missing"), warn("dirty-tree")], "release", pending=False, pre_tag=True))
    assert found == {"tag-missing": "warn", "dirty-tree": "block"}


def test_pre_tag_flag_reaches_the_cli(tmp_path: Path, capsys):
    repo = make_repo(tmp_path)
    validate.main([str(repo), "--profile", "release", "--pre-tag", "--json"])
    import json
    findings = json.loads(capsys.readouterr().out)["findings"]
    tag = [f for f in findings if f["code"] == "tag-missing"]
    assert all(f["severity"] == "warn" for f in tag)


def test_dirty_tree_blocks_outside_a_bump():
    assert validate.escalate([warn("dirty-tree")], "public", pending=False)[0].severity == "block"


def test_escalation_marks_the_message():
    finding = validate.escalate([warn("ci-missing")], "public", pending=False)[0]
    assert finding.message.endswith("(required)")


def test_every_kept_warning_has_a_reason():
    assert all(reason.strip() for reason in validate.KEEP_WARN.values())


def test_unparseable_package_json_blocks(tmp_path: Path):
    repo = make_repo(tmp_path)
    (repo / "package.json").write_text("{ not json")
    _, extra = domains.check_domain(repo, "auto")
    assert severities(extra).get("package-json-invalid") == "block"
