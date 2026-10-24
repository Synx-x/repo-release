#!/usr/bin/env python3
"""Check that a repository is fit to be published, or fit to be released.

Two profiles:

    public    everything a stranger judges in the first screen, plus the
              leaks that only matter once the repo is readable by anyone
    release   the public set, plus version, tag and changelog coherence

Exit codes: 0 clean or warnings only, 1 a blocking finding, 2 usage error.

    python3 validate.py /path/to/repo --profile public
    python3 validate.py . --profile release --json

The skills in this plugin explain why each check exists. This file only says
whether it holds. Keeping the judgment out of it means the same answer every
run, and the hook can depend on the exit code.

Read-only. Nothing here writes to the target repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

README_NAMES = ("README.md", "README.rst", "README.txt", "README")
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")
BRIDGE_NAMES = ("CLAUDE.md", "GEMINI.md", ".cursorrules")
AGENT_FACING = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "CONTRIBUTING.md",
    "README.md",
)
MIN_README_BYTES = 400

# Machine-local path shapes. A shared repo must resolve these from the repo
# root, never from one author's home directory.
#
# `~/...` is deliberately absent. A tilde path is portable by construction, and
# a README documenting that config lives at `~/.webbridge/config.toml` is
# correct. The defect is a path naming one author's home, which only resolves
# on their machine.
LOCAL_PATH = re.compile(
    r"(?<![\w./-])(?:"
    r"/home/[A-Za-z0-9_.-]+/|"
    r"/Users/[A-Za-z0-9_.-]+/|"
    r"/srv/[A-Za-z0-9_.-]+/home/|"
    r"/mnt/[A-Za-z0-9_.-]+/|"
    r"[A-Za-z]:\\\\Users\\\\"
    r")"
)

# Highest-signal credential shapes. Deliberately narrow: a broad pattern turns
# every placeholder in a README into a blocker and the check gets switched off.
SECRETS = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{24,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
)

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
             ".pytest_cache", "dist", "build", ".mypy_cache", ".ruff_cache"}

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
                 ".zip", ".gz", ".tar", ".whl", ".so", ".pyc", ".lock"}


@dataclass
class Finding:
    severity: str      # block | warn | note
    code: str
    message: str
    path: str = ""

    def line(self) -> str:
        where = f" [{self.path}]" if self.path else ""
        return f"{self.severity.upper():5s} {self.code}: {self.message}{where}"


def git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout if out.returncode == 0 else ""


def is_git(repo: Path) -> bool:
    return git(repo, "rev-parse", "--git-dir").strip() != ""


def tracked(repo: Path) -> list[str]:
    return [p for p in git(repo, "ls-files").splitlines() if p]


def walk(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def first_existing(repo: Path, names) -> Path | None:
    for name in names:
        candidate = repo / name
        if candidate.exists():
            return candidate
    return None


# --- checks ---------------------------------------------------------------

def check_surface(repo: Path) -> list[Finding]:
    """The four things GitHub shows before anyone reads a line of code."""
    out = []
    readme = first_existing(repo, README_NAMES)
    if readme is None:
        out.append(Finding("block", "readme-missing",
                           "no README; the repo has no first screen"))
    else:
        size = len(readme.read_text(encoding="utf-8", errors="replace"))
        if size < MIN_README_BYTES:
            out.append(Finding("block", "readme-thin",
                               f"README is {size} bytes, under {MIN_README_BYTES}; "
                               "it does not yet say what this is and how to install it",
                               readme.name))
        else:
            out.append(Finding("note", "readme-ok", f"README present, {size} bytes",
                               readme.name))

    license_file = first_existing(repo, LICENSE_NAMES)
    if license_file is None:
        out.append(Finding("block", "license-missing",
                           "no LICENSE; nobody can legally reuse this"))
    else:
        text = read(license_file)
        if len(text.strip()) < 40:
            out.append(Finding("block", "license-thin",
                               "LICENSE exists but carries almost no text", license_file.name))
        else:
            out.append(Finding("note", "license-ok", "license present", license_file.name))
    return out


def check_ignored_tracked(repo: Path) -> list[Finding]:
    """Files git would ignore but is still tracking. Usually a build artefact
    committed before the ignore rule existed."""
    if not is_git(repo):
        return [Finding("note", "git-missing", "not a git repository; skipped git checks")]
    out = []
    ignored = git(repo, "ls-files", "-i", "-c", "--exclude-standard").splitlines()
    for path in [p for p in ignored if p]:
        out.append(Finding("block", "ignored-but-tracked",
                           "tracked although .gitignore excludes it", path))
    if not out:
        out.append(Finding("note", "ignored-clean", "no tracked file is excluded by .gitignore"))
    return out


def check_absolute_paths(repo: Path) -> list[Finding]:
    """An instruction pointing outside the repo resolves to nothing on another
    machine, and no one ever finds out."""
    out = []
    targets = [repo / name for name in AGENT_FACING if (repo / name).exists()]
    rules = repo / ".agents" / "rules"
    if rules.is_dir():
        targets.extend(sorted(rules.glob("*.md")))
    for path in targets:
        for number, line in enumerate(read(path).splitlines(), start=1):
            seen: set[str] = set()
            for match in LOCAL_PATH.finditer(line):
                token = match.group(0)
                if token in seen:
                    continue
                seen.add(token)
                out.append(Finding(
                    "block", "absolute-path",
                    f"line {number}: machine-local path {token!r}; "
                    "vendor the file into the repo or drop the reference",
                    path.relative_to(repo).as_posix(),
                ))
    if not out:
        out.append(Finding("note", "absolute-path-clean",
                           "no machine-local path in agent-facing files"))
    return out


def check_secrets(repo: Path) -> list[Finding]:
    out = []
    for path in walk(repo):
        text = read(path)
        if not text:
            continue
        for name, pattern in SECRETS:
            match = pattern.search(text)
            if match:
                rel = path.relative_to(repo).as_posix()
                out.append(Finding("block", "secret",
                                   f"{name} match; rotate it before publishing",
                                   rel))
                break
    if not out:
        out.append(Finding("note", "secret-clean", "no credential shape found in tracked text"))
    return out


def check_cited_paths(repo: Path) -> list[Finding]:
    """A rule that cites a moved file teaches an agent something false.

    Only tokens shaped like a repo path are checked. A dotted backtick span is
    usually a symbol, a method or a config key, and reporting those as missing
    files buries the real finding.
    """
    out = []
    sources = [repo / "AGENTS.md"]
    rules = repo / ".agents" / "rules"
    if rules.is_dir():
        sources.extend(sorted(rules.glob("*.md")))
    cited = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]+)`")
    missing = 0
    for path in [p for p in sources if p.exists()]:
        for token in cited.findall(read(path)):
            if token.startswith(("http", "/", "~")):
                continue
            if "/" not in token and "*" not in token:
                continue    # a bare dotted name is a symbol, not a file
            if "*" in token:
                if not list(repo.glob(token)):
                    missing += 1
                    out.append(Finding("warn", "cited-path-missing",
                                       f"glob {token!r} matches nothing",
                                       path.relative_to(repo).as_posix()))
                continue
            if not (repo / token).exists():
                missing += 1
                out.append(Finding("warn", "cited-path-missing",
                                   f"cites {token!r} which does not exist",
                                   path.relative_to(repo).as_posix()))
    if not missing:
        out.append(Finding("note", "cited-paths-ok", "every cited path resolves"))
    return out


# Covers os.environ["X"], os.environ.get("X"), os.getenv("X"), env("X") and
# process.env.X. A narrower pattern misses the getenv form, which is the common
# one in Python and produces a false all-clear.
ENV_IN_CODE = re.compile(
    r"""(?:os\.environ(?:\.get)?\s*[([]\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|os\.getenv\s*\(\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|env\s*\(\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|process\.env\.([A-Z][A-Z0-9_]{2,}))"""
)


def check_env_example(repo: Path) -> list[Finding]:
    sample = repo / ".env.example"
    found: set[str] = set()
    for path in walk(repo):
        if path.name == ".env.example":
            continue
        # A fixture that contains os.getenv("X") is data, not a real read. Counting
        # it demands documentation for a variable nothing actually reads.
        if "tests" in path.relative_to(repo).parts or "fixtures" in path.relative_to(repo).parts:
            continue
        if path.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"):
            continue
        for groups in ENV_IN_CODE.findall(read(path)):
            for name in groups:
                if name:
                    found.add(name)
    if not found:
        return [Finding("note", "env-none", "no environment variables read by the source")]
    if not sample.exists():
        return [Finding("block", "env-example-missing",
                        f"source reads {len(found)} environment variable(s) but there is "
                        "no .env.example listing them")]
    listed = sample.read_text(encoding="utf-8", errors="replace")
    missing = sorted(name for name in found if name not in listed)
    out = []
    for name in missing:
        out.append(Finding("warn", "env-undocumented",
                           f"{name} is read by the source but not in .env.example",
                           ".env.example"))
    if not missing:
        out.append(Finding("note", "env-ok", f"all {len(found)} variable(s) documented"))
    return out


def check_agents_md(repo: Path) -> list[Finding]:
    out = []
    agents = repo / "AGENTS.md"
    if not agents.exists():
        out.append(Finding("warn", "agents-md-missing",
                           "no AGENTS.md; every AI tool has to rediscover the conventions"))
        return out
    out.append(Finding("note", "agents-md-ok", "AGENTS.md present"))
    for name in BRIDGE_NAMES:
        bridge = repo / name
        if not bridge.exists():
            continue
        text = read(bridge)
        if "AGENTS.md" not in text:
            out.append(Finding("warn", "bridge-diverges",
                               "exists but does not import AGENTS.md; it will drift",
                               name))
        elif len([ln for ln in text.splitlines() if ln.strip()]) > 12:
            out.append(Finding("warn", "bridge-long",
                               "bridge is over 12 lines; it should import AGENTS.md, not restate it",
                               name))
    return out


def check_hygiene(repo: Path) -> list[Finding]:
    out = []
    if not (repo / ".gitignore").exists():
        out.append(Finding("block", "gitignore-missing",
                           "no .gitignore; build output and local config will be committed"))
    for path in tracked(repo):
        if path.startswith(".venv/") or "/.venv/" in path or path.startswith("node_modules/"):
            out.append(Finding("block", "vendored-deps",
                               "dependency tree is tracked; nothing else in the repo is judged fairly",
                               path))
            break
    if not is_git(repo):
        return out
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    dirty = git(repo, "status", "--porcelain").strip()
    if dirty:
        out.append(Finding("warn", "dirty-tree",
                           "uncommitted changes; what you publish is not what you tested"))
    out.append(Finding("note", "branch", f"on branch {branch or 'detached'}"))
    if not out:
        out.append(Finding("note", "hygiene-ok", "ignore rules and tree state are clean"))
    return out


def check_release(repo: Path, expected: str = "") -> list[Finding]:
    """Version, tag and changelog must point at the same release.

    `expected` is the version a pending edit is about to write. The file on disk
    still holds the old one, so without it a version bump is always judged
    against the release it is replacing and always passes.
    """
    out = []
    version, source = None, ""
    pyproject = repo / "pyproject.toml"
    package = repo / "package.json"
    plugin = repo / ".claude-plugin" / "plugin.json"
    if pyproject.exists():
        match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']',
                          read(pyproject), re.MULTILINE)
        if match:
            version, source = match.group(1), "pyproject.toml"
    if version is None and package.exists():
        try:
            version, source = json.loads(read(package)).get("version"), "package.json"
        except json.JSONDecodeError:
            pass
    if version is None and plugin.exists():
        try:
            version = json.loads(read(plugin)).get("version")
            source = ".claude-plugin/plugin.json"
        except json.JSONDecodeError:
            pass
    if version is None:
        out.append(Finding("block", "version-missing",
                           "no version in pyproject.toml, package.json or plugin.json"))
        return out
    if expected and expected != version:
        out.append(Finding("note", "version-pending",
                           f"checking the pending version {expected}, not {version} on disk"))
        version, source = expected, "pending edit"
    out.append(Finding("note", "version", f"{version} from {source}"))

    if re.fullmatch(r"0\.0\.0", version or ""):
        out.append(Finding("block", "version-placeholder",
                           "version is 0.0.0; set the version you mean to ship"))

    changelog = first_existing(repo, ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"))
    if changelog is None:
        out.append(Finding("block", "changelog-missing",
                           "no CHANGELOG.md; a release with no recorded change is a bare tag"))
    elif version not in read(changelog):
        out.append(Finding("block", "changelog-stale",
                           f"CHANGELOG does not mention version {version}", changelog.name))
    else:
        out.append(Finding("note", "changelog-ok", f"CHANGELOG covers {version}",
                           changelog.name))

    if is_git(repo):
        tags = git(repo, "tag", "--list", f"v{version}").strip()
        if not tags:
            out.append(Finding("warn", "tag-missing",
                               f"no tag v{version}; release it with "
                               f"`git tag -a v{version} -m ...`"))
        else:
            out.append(Finding("note", "tag-ok", f"tag v{version} exists"))
    return out


PROFILES = {
    "public": (
        check_surface, check_ignored_tracked, check_absolute_paths,
        check_secrets, check_cited_paths, check_env_example,
        check_agents_md, check_hygiene,
    ),
    "release": (
        check_surface, check_ignored_tracked, check_absolute_paths,
        check_secrets, check_cited_paths, check_env_example,
        check_agents_md, check_hygiene, check_release,
    ),
}


def run(repo: Path, profile: str, expected: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for check in PROFILES[profile]:
        try:
            if check is check_release:
                findings.extend(check(repo, expected))
            else:
                findings.extend(check(repo))
        except Exception as exc:  # a broken check must not hide the others
            findings.append(Finding("warn", "check-error",
                                    f"{check.__name__} failed: {exc}"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate",
        description="Check a repository against the publish surface and release discipline.",
    )
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="public")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="blocking findings only")
    parser.add_argument(
        "--version",
        default="",
        help="check this version instead of the one on disk, for a pending bump",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="domain gate to apply: auto to detect, a name to force, empty to skip",
    )
    parser.add_argument("--list-domains", action="store_true",
                        help="print the domains this can detect, then exit")
    args = parser.parse_args(argv)

    if args.list_domains:
        import domains as domain_mod
        for name, marker in domain_mod.list_domains():
            print(f"{name:16} {marker}")
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2

    findings = run(repo, args.profile, args.version)
    resolved = ""
    if args.domain:
        import domains as domain_mod
        resolved, extra = domain_mod.check_domain(repo, args.domain)
        findings.extend(extra)
    blocking = [f for f in findings if f.severity == "block"]
    warnings = [f for f in findings if f.severity == "warn"]

    if args.json:
        print(json.dumps({
            "repo": str(repo),
            "profile": args.profile,
            "domain": resolved,
            "ok": not blocking,
            "counts": {"block": len(blocking), "warn": len(warnings)},
            "findings": [asdict(f) for f in findings],
        }, indent=2))
    else:
        shown = blocking + warnings if args.quiet else findings
        for finding in shown:
            print(finding.line())
        print()
        verdict = "READY" if not blocking else "NOT READY"
        domain_note = f", domain {resolved}" if resolved else ""
        print(f"{verdict}: {len(blocking)} blocking, {len(warnings)} warning(s) "
              f"for profile {args.profile}{domain_note}")

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
