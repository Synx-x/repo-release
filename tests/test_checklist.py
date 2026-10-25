"""Tests for the checklist gate.

The drift test is the one that matters most. A skill that gains a checklist
line the gate does not map is advice nothing enforces again, which is the
defect this file exists to close.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import checklist  # noqa: E402

GOOD_README = "# thing\n\n" + ("Installs with pip. Then it does the job you named. " * 12)


def skill_lines() -> set[tuple[str, str]]:
    found = set()
    for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"):
        text = path.read_text()
        section = text.split("## Checklist", 1)[1] if "## Checklist" in text else ""
        for line in re.findall(r"^- \[ \] (.+)$", section, re.MULTILINE):
            found.add((path.parent.name, line.strip()))
    return found


def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(GOOD_README)
    (repo / "LICENSE").write_text("MIT License\n\n" + "Permission is hereby granted. " * 8)
    (repo / ".gitignore").write_text("__pycache__/\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    commit(repo, "first")
    return repo


def commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", message], cwd=repo, check=True)


def status(repo: Path, item_id: str, profile: str = "release") -> str:
    rows = {item.id: s for item, s, _ in checklist.evaluate(repo, profile)}
    return rows[item_id]


# --- drift ----------------------------------------------------------------

def test_every_skill_checklist_line_is_gated():
    mapped = {(item.skill, item.text) for item in checklist.ITEMS}
    missing = skill_lines() - mapped
    assert not missing, f"skill lines with no gate item: {sorted(missing)}"


def test_every_gate_item_quotes_a_real_skill_line():
    stale = {(item.skill, item.text) for item in checklist.ITEMS} - skill_lines()
    assert not stale, f"gate items whose skill line changed or vanished: {sorted(stale)}"


def test_item_ids_are_unique():
    ids = [item.id for item in checklist.ITEMS]
    assert len(ids) == len(set(ids))


# --- attestations ---------------------------------------------------------

def test_an_unattested_judgement_blocks(tmp_path: Path):
    assert status(git_repo(tmp_path), "gaps-written") == "attest"


def test_attestation_passes_on_its_own_commit(tmp_path: Path):
    repo = git_repo(tmp_path)
    assert checklist.record(repo, "gaps-written", "no open gaps: README Limits lists two") == 0
    assert status(repo, "gaps-written") == "pass"


def test_a_new_commit_voids_the_attestation(tmp_path: Path):
    repo = git_repo(tmp_path)
    checklist.record(repo, "gaps-written", "no open gaps: README Limits lists two")
    commit(repo, "second")
    assert status(repo, "gaps-written") == "attest"


def test_a_thin_attestation_is_refused(tmp_path: Path):
    repo = git_repo(tmp_path)
    assert checklist.record(repo, "gaps-written", "done") == 2
    assert status(repo, "gaps-written") == "attest"


def test_an_auto_item_cannot_be_attested(tmp_path: Path):
    assert checklist.record(git_repo(tmp_path), "tag-annotated", "trust me, it is tagged") == 2


def test_attestations_stay_out_of_the_tree(tmp_path: Path):
    repo = git_repo(tmp_path)
    checklist.record(repo, "gaps-written", "no open gaps: README Limits lists two")
    assert not subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                              capture_output=True, text=True).stdout.strip()


# --- auto items -----------------------------------------------------------

def test_a_crashed_check_is_a_fail(tmp_path: Path, monkeypatch):
    def broken(repo):
        raise RuntimeError("boom")
    item = next(i for i in checklist.ITEMS if i.id == "license")
    monkeypatch.setattr(item, "check", broken)
    assert status(git_repo(tmp_path), "license") == "fail"


def test_lightweight_tag_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0]\n\n- x\n")
    commit(repo, "release 0.1.0")
    subprocess.run(["git", "tag", "v0.1.0"], cwd=repo, check=True)
    assert status(repo, "tag-annotated") == "fail"
    subprocess.run(["git", "tag", "-d", "v0.1.0"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "tag", "-a",
                    "v0.1.0", "-m", "0.1.0"], cwd=repo, check=True)
    assert status(repo, "tag-annotated") == "pass"


def test_version_and_changelog_in_separate_commits_fail(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    commit(repo, "version")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0]\n\n- x\n")
    commit(repo, "changelog")
    assert status(repo, "committed-together") == "fail"


def test_version_and_changelog_in_one_commit_pass(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0]\n\n- x\n")
    commit(repo, "release")
    assert status(repo, "committed-together") == "pass"


def test_missing_unreleased_section_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n\n- x\n")
    assert status(repo, "unreleased") == "fail"
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## 0.1.0\n")
    assert status(repo, "unreleased") == "pass"


def test_a_break_without_migration_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
    (repo / "CHANGELOG.md").write_text("## [2.0.0]\n\n- Removed the --fast flag.\n")
    assert status(repo, "migration") == "fail"
    (repo / "CHANGELOG.md").write_text(
        "## [2.0.0]\n\n- Removed the --fast flag. Use --mode fast instead.\n")
    assert status(repo, "migration") == "pass"


def test_ci_without_the_ignore_gate_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / ".github" / "workflows").mkdir(parents=True)
    ci = repo / ".github" / "workflows" / "ci.yml"
    ci.write_text("jobs:\n  t:\n    steps:\n      - run: python -m pytest\n")
    assert status(repo, "ci-shape") == "fail"
    ci.write_text(ci.read_text() + "      - run: git ls-files -i -c --exclude-standard\n")
    assert status(repo, "ci-shape") == "pass"


def test_tracked_build_output_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "dist").mkdir()
    (repo / "dist" / "thing.whl").write_text("x")
    subprocess.run(["git", "add", "-f", "dist"], cwd=repo, check=True)
    assert status(repo, "no-build-output") == "fail"


def test_a_missing_agents_md_fails_instead_of_skipping(tmp_path: Path):
    assert status(git_repo(tmp_path), "golden-rules") == "fail"


# --- nothing is skipped silently ------------------------------------------

def test_an_inapplicable_item_needs_a_review(tmp_path: Path):
    assert status(git_repo(tmp_path), "domains-agree") == "attest"


def test_one_skill_review_covers_every_item_in_it(tmp_path: Path):
    repo = git_repo(tmp_path)
    assert checklist.record(repo, "na:domain-gates",
                            "a CLI with no domain detector, so no gate to build") == 0
    rows = {i.id: s for i, s, _ in checklist.evaluate(repo, "release") if i.skill == "domain-gates"}
    assert set(rows.values()) == {"na"}


def test_an_item_review_covers_only_that_item(tmp_path: Path):
    repo = git_repo(tmp_path)
    checklist.record(repo, "na:precedence", "no detector list exists in this repo at all")
    assert status(repo, "precedence") == "na"
    assert status(repo, "domains-agree") == "attest"


# --- scaffold and domain review -------------------------------------------

def scaffolded(tmp_path: Path) -> Path:
    repo = git_repo(tmp_path)
    subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "scaffold.py"), str(repo),
                    "--name", "thing", "--owner", "me", "--repo-url", "https://x/y"],
                   check=True, capture_output=True)
    return repo


def test_an_unscaffolded_repo_fails(tmp_path: Path):
    assert status(git_repo(tmp_path), "scaffold-complete") == "fail"


def test_a_raw_scaffold_fails_on_its_placeholders(tmp_path: Path):
    rows = {i.id: (s, d) for i, s, d in checklist.evaluate(scaffolded(tmp_path), "public")}
    state, detail = rows["scaffold-complete"]
    assert state == "fail" and "placeholder left" in detail


def test_a_filled_scaffold_passes(tmp_path: Path):
    repo = scaffolded(tmp_path)
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            text = path.read_text()
            path.write_text(checklist.PLACEHOLDER.sub("filled", text))
    assert status(repo, "scaffold-complete") == "pass"


def test_domain_review_must_name_the_detected_domain(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    commit(repo, "pyproject")
    checklist.record(repo, "domain-review", "reviewed the repo and added what it needs")
    assert status(repo, "domain-review") == "attest"
    checklist.record(repo, "domain-review",
                     "python-library: added tests/ and requires-python; no py.typed, untyped")
    assert status(repo, "domain-review") == "pass"


def test_golden_rule_without_a_rule_file_fails(tmp_path: Path):
    repo = git_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# A\n\n## Golden rules\n\n1. **Be good.** Always.\n")
    assert status(repo, "golden-rules") == "fail"
    (repo / ".agents" / "rules").mkdir(parents=True)
    (repo / ".agents" / "rules" / "good.md").write_text("# Good\n")
    (repo / "AGENTS.md").write_text(
        "# A\n\n## Golden rules\n\n1. **Be good.** See `.agents/rules/good.md`.\n")
    assert status(repo, "golden-rules") == "pass"


def test_the_cli_exits_one_when_blocked(tmp_path: Path):
    out = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "checklist.py"),
                          str(git_repo(tmp_path)), "--profile", "public"],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "BLOCKED" in out.stdout
