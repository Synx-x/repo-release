"""Tests for the README voice and structure gate.

A published README describes the project, not the author's machine. These
fixtures each hold one defect, so a pass means the check discriminates.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate  # noqa: E402

BODY = "The service converts text to speech and exposes a socket for clients. " * 8

DIAGRAM = "\n```mermaid\nflowchart LR\n  A --> B\n```\n"
TREE = "\n```text\nrepo/\n├── src/\n└── tests/\n```\n"


def make_repo(tmp_path: Path, readme: str, dirs: int = 2) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(readme)
    for index in range(dirs):
        folder = repo / f"pkg{index}"
        folder.mkdir()
        (folder / "mod.py").write_text("x = 1\n")
    return repo


def codes(findings) -> dict[str, str]:
    return {f.code: f.severity for f in findings}


# --- environment language ---------------------------------------------------

def test_clean_readme_passes(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + DIAGRAM + TREE)
    found = codes(validate.check_readme_voice(repo))
    assert "readme-environment" not in found
    assert "readme-first-person" not in found
    assert found.get("readme-voice-ok") == "note"


def test_gpu_model_blocks(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nIt runs well on an RTX 3050 laptop GPU.\n")
    assert codes(validate.check_readme_voice(repo)).get("readme-environment") == "block"


def test_tested_on_blocks(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nMeasured on a 4 GB card, 2026-11-03.\n")
    assert codes(validate.check_readme_voice(repo)).get("readme-environment") == "block"


def test_my_machine_blocks(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nThis works on my laptop.\n")
    found = codes(validate.check_readme_voice(repo))
    assert found.get("readme-environment") == "block"


def test_hardware_requirement_is_allowed(tmp_path: Path):
    """A requirement names what a user needs, which is the README's job."""
    repo = make_repo(tmp_path, "# tool\n\n" + BODY
                     + "\nRequires an NVIDIA GPU, RTX 2060 or newer recommended.\n")
    assert "readme-environment" not in codes(validate.check_readme_voice(repo))


def test_requirement_line_does_not_excuse_a_test_report(tmp_path: Path):
    """The requirement escape covers a model name, never a `tested on` report."""
    repo = make_repo(tmp_path, "# tool\n\n" + BODY
                     + "\nRequires an NVIDIA GPU, tested on a 4 GB card.\n")
    assert codes(validate.check_readme_voice(repo)).get("readme-environment") == "block"


def test_code_blocks_are_not_prose(tmp_path: Path):
    readme = "# tool\n\n" + BODY + "\n```bash\n# tested on my machine with an RTX 3050\nrun\n```\n"
    repo = make_repo(tmp_path, readme)
    found = codes(validate.check_readme_voice(repo))
    assert "readme-environment" not in found
    assert "readme-first-person" not in found


# --- first person -----------------------------------------------------------

def test_first_person_blocks(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nI built this because my old setup broke.\n")
    assert codes(validate.check_readme_voice(repo)).get("readme-first-person") == "block"


def test_io_is_not_first_person(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nThe daemon does blocking I/O on a thread.\n")
    assert "readme-first-person" not in codes(validate.check_readme_voice(repo))


def test_finding_names_the_line(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\nTested on my desktop.\n")
    messages = [f.message for f in validate.check_readme_voice(repo) if f.severity == "block"]
    assert any("line 4" in message for message in messages)


# --- structure --------------------------------------------------------------

def test_missing_diagram_and_tree_block_a_multi_directory_repo(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY)
    found = codes(validate.check_readme_structure(repo))
    assert found.get("readme-diagram-missing") == "block"
    assert found.get("readme-tree-missing") == "block"


def test_single_directory_repo_only_warns(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY, dirs=0)
    found = codes(validate.check_readme_structure(repo))
    assert found.get("readme-diagram-missing") == "warn"
    assert found.get("readme-tree-missing") == "warn"


def test_mermaid_and_tree_pass(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + DIAGRAM + TREE)
    found = codes(validate.check_readme_structure(repo))
    assert "readme-diagram-missing" not in found
    assert "readme-tree-missing" not in found
    assert found.get("readme-structure-ok") == "note"


def test_diagram_image_counts(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY + "\n![Architecture](docs/architecture.svg)\n" + TREE)
    assert "readme-diagram-missing" not in codes(validate.check_readme_structure(repo))


def test_dot_and_skipped_dirs_do_not_count(tmp_path: Path):
    repo = make_repo(tmp_path, "# tool\n\n" + BODY, dirs=1)
    (repo / ".github").mkdir()
    (repo / "node_modules").mkdir()
    found = codes(validate.check_readme_structure(repo))
    assert found.get("readme-tree-missing") == "warn"


# --- the About description --------------------------------------------------

def test_description_findings():
    assert validate.voice_findings("Local TTS service with voice cloning") == []
    assert validate.voice_findings("TTS tested on my RTX 3050 laptop")
    assert validate.voice_findings("A tool I wrote for myself")


def test_profiles_carry_the_gate():
    for profile in ("public", "release"):
        assert validate.check_readme_voice in validate.PROFILES[profile]
        assert validate.check_readme_structure in validate.PROFILES[profile]
