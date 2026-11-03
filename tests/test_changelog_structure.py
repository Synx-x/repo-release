"""The changelog keeps the Keep a Changelog shape the template sets.

Each fixture breaks one part of the shape, so a pass means the check reads
structure rather than only finding the current version.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate  # noqa: E402

HEADER = """# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""
GOOD = HEADER + """## [Unreleased]

## [1.1.0] - 2026-10-27

### Added

- A flag.

### Changed

- A behaviour.

## [1.0.0] - 2026-10-20

### Added

- The first release.

[Unreleased]: https://github.com/x/y/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/x/y/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/x/y/releases/tag/v1.0.0
"""


def make_repo(tmp_path: Path, changelog: str | None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    if changelog is not None:
        (repo / "CHANGELOG.md").write_text(changelog)
    return repo


def codes(repo: Path) -> dict[str, str]:
    return {f.code: f.severity for f in validate.check_changelog_structure(repo)}


def test_template_shape_passes(tmp_path: Path):
    assert codes(make_repo(tmp_path, GOOD)) == {"changelog-structure-ok": "note"}


def test_missing_changelog_blocks(tmp_path: Path):
    assert codes(make_repo(tmp_path, None)).get("changelog-missing") == "block"


def test_missing_format_statement_blocks(tmp_path: Path):
    text = GOOD.replace("The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),\n", "")
    assert codes(make_repo(tmp_path, text)).get("changelog-format-unstated") == "block"


def test_missing_unreleased_blocks(tmp_path: Path):
    text = GOOD.replace("## [Unreleased]\n\n", "").replace("[Unreleased]: https://github.com/x/y/compare/v1.1.0...HEAD\n", "")
    assert codes(make_repo(tmp_path, text)).get("changelog-unreleased-missing") == "block"


def test_unbracketed_version_heading_blocks(tmp_path: Path):
    text = GOOD.replace("## [1.0.0] - 2026-10-20", "## 1.0.0 - 2026-10-20")
    assert codes(make_repo(tmp_path, text)).get("changelog-heading-shape") == "block"


def test_version_without_category_blocks(tmp_path: Path):
    text = GOOD.replace("## [1.0.0] - 2026-10-20\n\n### Added\n\n", "## [1.0.0] - 2026-10-20\n\n")
    assert codes(make_repo(tmp_path, text)).get("changelog-category-missing") == "block"


def test_unknown_category_blocks(tmp_path: Path):
    text = GOOD.replace("### Changed", "### Improvements")
    assert codes(make_repo(tmp_path, text)).get("changelog-category-unknown") == "block"


def test_missing_link_reference_blocks(tmp_path: Path):
    text = GOOD.replace("[1.0.0]: https://github.com/x/y/releases/tag/v1.0.0\n", "")
    found = validate.check_changelog_structure(make_repo(tmp_path, text))
    missing = [f for f in found if f.code == "changelog-link-missing"]
    assert missing and "1.0.0" in missing[0].message


def test_profiles_carry_the_check():
    for profile in ("public", "release"):
        assert validate.check_changelog_structure in validate.PROFILES[profile]
