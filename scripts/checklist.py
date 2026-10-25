#!/usr/bin/env python3
"""Hold a publish or release to every checklist item the skills name.

The skills end in a `## Checklist`. Before this file, those lines were advice:
the validator checked files, and nothing checked whether the steps were done.
An agent that skipped a step met no resistance. This file turns each line into
a gate item the hook runs.

Three kinds of item:

    auto     code decides, every run, from the tree, git or the validator
    remote   code decides from GitHub, through `gh`, or from the network
    attest   a judgement only a reader can make. It passes only with a
             written attestation recorded against the current HEAD commit

An attestation is per commit. A new commit voids every attestation, so a
judgement made about an older tree never carries over to a newer one.

    python3 checklist.py /path/to/repo --profile release
    python3 checklist.py . attest readme-lead --evidence "README opens with ..."
    python3 checklist.py --list

`tests/test_checklist.py` fails when a skill gains a checklist line this file
does not map, so the gate cannot fall behind the skills.

Exit codes: 0 every applicable item holds, 1 an item fails, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MIN_EVIDENCE = 20

Result = tuple[str, str]   # (status, detail). status: pass | fail | na | attest


@dataclass
class Item:
    id: str
    skill: str
    text: str                     # the checklist line, verbatim from the skill
    profiles: tuple[str, ...]     # public, release
    kind: str                     # auto | remote | attest
    check: Callable[[Path], Result]


# --- helpers ----------------------------------------------------------------

def git(repo: Path, *args: str) -> str:
    return validate.git(repo, *args)


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def attest_file(repo: Path) -> Path | None:
    """Attestations live in the git dir, so they are never tracked or published."""
    git_dir = git(repo, "rev-parse", "--absolute-git-dir").strip()
    if not git_dir:
        return None
    return Path(git_dir) / "repo-release" / "attest.json"


def load_attestations(repo: Path) -> dict:
    path = attest_file(repo)
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def attested(repo: Path, item_id: str) -> Result:
    record = load_attestations(repo).get(item_id)
    if not record:
        return "attest", "needs a reader's judgement: record it with `checklist.py attest`"
    if record.get("sha") != head(repo):
        return "attest", "attested on an older commit; re-check and attest again"
    return "pass", f"attested: {record.get('evidence', '')[:90]}"


def findings(repo: Path, check) -> list:
    try:
        return check(repo)
    except Exception as exc:  # a crashed check is not a pass
        return [validate.Finding("block", "check-error", str(exc))]


def none_of(repo: Path, check, severities=("block",), codes=()) -> Result:
    bad = [f for f in findings(repo, check)
           if f.severity in severities or f.code in codes]
    if bad:
        return "fail", "; ".join(f"{f.code}: {f.message}" for f in bad[:3])
    return "pass", ""


def readme(repo: Path) -> str:
    path = validate.first_existing(repo, validate.README_NAMES)
    return validate.read(path) if path else ""


def version(repo: Path) -> tuple[str, str]:
    for f in validate.check_release(repo):
        if f.code == "version":
            match = re.match(r"(\S+) from (.+)", f.message)
            if match:
                return match.group(1), match.group(2)
    return "", ""


def changelog(repo: Path) -> Path | None:
    return validate.first_existing(repo, ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"))


def changelog_section(repo: Path, ver: str) -> str:
    path = changelog(repo)
    if not path or not ver:
        return ""
    text = validate.read(path)
    match = re.search(rf"^##[^\n]*\b{re.escape(ver)}\b[^\n]*\n(.*?)(?=^## |\Z)",
                      text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def gh_json(repo: Path, *args: str) -> dict | list | None:
    try:
        out = subprocess.run(["gh", *args], cwd=repo, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def has_remote(repo: Path) -> bool:
    return "github.com" in git(repo, "remote", "get-url", "origin")


def workflows(repo: Path) -> str:
    folder = repo / ".github" / "workflows"
    if not folder.is_dir():
        return ""
    return "\n".join(validate.read(p) for p in sorted(folder.glob("*.y*ml")))


# --- auto checks ------------------------------------------------------------

def validator_ok(profile: str) -> Callable[[Path], Result]:
    def check(repo: Path) -> Result:
        bad = [f for f in validate.run(repo, profile) if f.severity == "block"]
        try:
            import domains
            bad += [f for f in domains.check_domain(repo, "auto")[1]
                    if f.severity == "block"]
        except Exception as exc:
            bad.append(validate.Finding("block", "domain-error", str(exc)))
        if bad:
            return "fail", "; ".join(f"{f.code}: {f.message}" for f in bad[:3])
        return "pass", f"validator clean on --profile {profile}"
    return check


def readme_lead(repo: Path) -> Result:
    text = readme(repo)
    if not text:
        return "fail", "no README"
    body = [b.strip() for b in re.split(r"\n\s*\n", text)
            if b.strip() and not b.lstrip().startswith(("#", "<!--", "[!", "<p", "!["))]
    if not body:
        return "fail", "README has no prose paragraph"
    headings = [h.lower() for h in re.findall(r"^#{2,3}\s+(.+)$", text, re.MULTILINE)]
    install = next((i for i, h in enumerate(headings)
                    if re.search(r"install|setup|getting started|quick ?start", h)), None)
    options = next((i for i, h in enumerate(headings)
                    if re.search(r"option|config|flag|setting", h)), None)
    if install is None:
        return "fail", "no Install section"
    if options is not None and options < install:
        return "fail", "options come before install"
    has_image = bool(re.search(r"!\[[^\]]*\]\(|<img\s", text))
    if not has_image:
        status, detail = attested(repo, "readme-lead")
        if status != "pass":
            return status, "no image: attest that the repo has no visual surface, or add one"
        return status, detail
    return "pass", "lead paragraph, image, install before options"


def license_ok(repo: Path) -> Result:
    return none_of(repo, validate.check_surface, severities=(),
                   codes=("license-missing", "license-thin"))


def counts_ok(repo: Path) -> Result:
    return none_of(repo, validate.check_claimed_counts, codes=("claimed-count-stale",))


def ignored_clean(repo: Path) -> Result:
    if not validate.is_git(repo):
        return "fail", "not a git repo"
    out = git(repo, "ls-files", "-i", "-c", "--exclude-standard").strip()
    return ("fail", f"tracked yet ignored: {out.splitlines()[:3]}") if out else ("pass", "")


def env_ignored(repo: Path) -> Result:
    notes = {f.code for f in findings(repo, validate.check_env_example)}
    if "env-none" in notes:
        return "na", "the source reads no environment variable"
    status, detail = none_of(repo, validate.check_env_example)
    if status != "pass":
        return status, detail
    probe = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", ".env"])
    if probe.returncode != 0:
        return "fail", ".env is not ignored"
    sample = repo / ".env.example"
    if sample.exists():
        probe = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", ".env.example"])
        if probe.returncode == 0:
            return "fail", ".env.example is ignored, so it never ships"
    return "pass", ""


BUILD_OUTPUT = re.compile(
    r"(^|/)(node_modules|\.venv|venv|dist|build|target|__pycache__)/|\.pyc$|\.egg-info/")


def no_build_output(repo: Path) -> Result:
    bad = [p for p in validate.tracked(repo) if BUILD_OUTPUT.search(p)]
    return ("fail", f"tracked build output: {bad[:3]}") if bad else ("pass", "")


def history_secrets(repo: Path) -> Result:
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", "-p", "--all", "--no-color"],
                             capture_output=True, text=True, timeout=60, errors="replace")
        history = out.stdout
    except (OSError, subprocess.TimeoutExpired):
        return "fail", "could not read history"
    hits = [name for name, pattern in validate.SECRETS if pattern.search(history)]
    if not hits:
        return "pass", "no credential shape anywhere in history"
    status, detail = attested(repo, "secrets-rotated")
    if status != "pass":
        return status, f"history holds {', '.join(hits)}: attest that each was rotated"
    return status, detail


def ci_shape(repo: Path) -> Result:
    text = workflows(repo)
    if not text:
        return "fail", "no workflow in .github/workflows"
    if not re.search(r"pytest|npm (run )?test|cargo test|go test|unittest|\btest\b", text):
        return "fail", "no workflow runs the tests"
    if "ls-files -i" not in text:
        return "fail", "no workflow runs `git ls-files -i -c --exclude-standard`"
    return "pass", ""


def docs_indexed(repo: Path) -> Result:
    docs = repo / "docs"
    if not docs.is_dir():
        return "na", "no docs/"
    pages = [p for p in docs.glob("*.md") if p.name.lower() not in ("readme.md", "index.md")]
    if len(pages) <= 3:
        return "na", f"docs/ holds {len(pages)} document(s)"
    if not ((docs / "README.md").exists() or (docs / "index.md").exists()):
        return "fail", f"docs/ holds {len(pages)} documents and no README.md or index.md"
    return "pass", ""


BREAK = re.compile(r"\bbreak(s|ing)?\b|\bremoved?\b|\brenamed?\b", re.IGNORECASE)
MIGRATE = re.compile(r"migrat|upgrade|replace|instead|move to|switch to", re.IGNORECASE)


def migration_named(repo: Path) -> Result:
    ver, _ = version(repo)
    section = changelog_section(repo, ver)
    if not section:
        return "fail", f"no changelog section for {ver or 'the version'}"
    if BREAK.search(section) and not MIGRATE.search(section):
        return "fail", "the entry names a break and no migration step"
    return "pass", ""


def committed_together(repo: Path) -> Result:
    ver, source = version(repo)
    log = changelog(repo)
    if not ver or not log or source in ("", "pending edit"):
        return "fail", "no version or changelog to compare"
    commit = git(repo, "log", "-1", "--format=%H", "-S", ver, "--", source).strip()
    if not commit:
        return "fail", f"the version {ver} is not committed"
    touched = git(repo, "show", "--name-only", "--format=", commit).split()
    if log.name not in touched:
        return "fail", (f"{source} gained {ver} in {commit[:7]}, which does not touch "
                        f"{log.name}")
    return "pass", f"{commit[:7]} carries both"


def tag_ok(repo: Path) -> Result:
    ver, _ = version(repo)
    if not ver:
        return "fail", "no version"
    names = [n for n in (f"v{ver}", ver) if git(repo, "tag", "--list", n).strip()]
    if not names:
        return "fail", f"no tag v{ver}: `git tag -a v{ver} -m ...`"
    kind = git(repo, "cat-file", "-t", names[0]).strip()
    if kind != "tag":
        return "fail", f"{names[0]} is lightweight; use `git tag -a`"
    target = git(repo, "rev-list", "-n", "1", names[0]).strip()
    if target != head(repo):
        return "fail", f"{names[0]} does not point at HEAD"
    return "pass", f"annotated {names[0]} at HEAD"


def tag_shape(repo: Path) -> Result:
    ver, _ = version(repo)
    tags = [t for t in git(repo, "tag", "--list").split() if t not in (ver, f"v{ver}")]
    semver = [t for t in tags if re.fullmatch(r"v?\d+\.\d+\.\d+.*", t)]
    if not semver:
        return "pass", "first tag sets the shape"
    prefixed = sum(t.startswith("v") for t in semver) * 2 >= len(semver)
    mine = git(repo, "tag", "--list", f"v{ver}").strip()
    if prefixed != bool(mine):
        return "fail", f"existing tags {'are' if prefixed else 'are not'} v-prefixed"
    return "pass", ""


def unreleased_open(repo: Path) -> Result:
    path = changelog(repo)
    if not path:
        return "fail", "no changelog"
    if not re.search(r"^##\s*\[?Unreleased\]?", validate.read(path), re.MULTILINE | re.IGNORECASE):
        return "fail", f"no `## [Unreleased]` section in {path.name}"
    return "pass", ""


def bridges_ok(repo: Path) -> Result:
    bad = []
    for name in ("CLAUDE.md", "GEMINI.md"):
        path = repo / name
        if not path.exists():
            continue
        text = validate.read(path)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if "AGENTS.md" not in text:
            bad.append(f"{name} does not import AGENTS.md")
        elif len(lines) > 5:
            bad.append(f"{name} has {len(lines)} lines, over 5")
    return ("fail", "; ".join(bad)) if bad else ("pass", "")


def golden_rules(repo: Path) -> Result:
    text = validate.read(repo / "AGENTS.md")
    match = re.search(r"^##\s+Golden rules\s*\n(.*?)(?=^## |\Z)", text,
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not match:
        return "fail", "AGENTS.md has no `## Golden rules` section"
    rules = re.split(r"^\d+\.\s", match.group(1), flags=re.MULTILINE)[1:]
    if not rules:
        return "fail", "the Golden rules section lists no numbered rule"
    for n, rule in enumerate(rules, 1):
        cited = re.findall(r"`([^`\s]+\.md)`", rule)
        if not cited:
            return "fail", f"golden rule {n} points at no rule file"
        missing = [c for c in cited if not (repo / c).exists()]
        if missing:
            return "fail", f"golden rule {n} cites missing {missing[0]}"
    return "pass", f"{len(rules)} rule(s), each pointing at a rule file"


def rules_indexed(repo: Path) -> Result:
    folder = repo / ".agents" / "rules"
    if not folder.is_dir():
        return "na", "no .agents/rules/"
    text = validate.read(repo / "AGENTS.md")
    missing = [p.name for p in sorted(folder.glob("*.md")) if p.name not in text]
    return ("fail", f"AGENTS.md never names {missing}") if missing else ("pass", "")


def cited_paths(repo: Path) -> Result:
    return none_of(repo, validate.check_cited_paths, codes=("cited-path-missing",))


def absolute_paths(repo: Path) -> Result:
    return none_of(repo, validate.check_absolute_paths)


def env_covered(repo: Path) -> Result:
    return none_of(repo, validate.check_env_example, severities=("block", "warn"))


def checks_tested(repo: Path) -> Result:
    """A check counts as tested when a test names it or a finding code it emits.

    A test can reach a check through `check_domain` or `run` without naming the
    function, so the codes it asserts on count too.
    """
    tests = "\n".join(validate.read(p) for p in (repo / "tests").glob("*.py"))
    untested = []
    for script in ("scripts/domains.py", "scripts/validate.py"):
        source = validate.read(repo / script)
        for match in re.finditer(r"^def (check_\w+)\(.*?(?=^def |\Z)", source,
                                 re.MULTILINE | re.DOTALL):
            name, body = match.group(1), match.group(0)
            codes = re.findall(r'Finding\(\s*"(?:block|warn)",\s*"([\w-]+)"', body)
            if name not in tests and not any(f'"{c}"' in tests for c in codes):
                untested.append(name)
    return ("fail", f"no test names {untested[:4]}") if untested else ("pass", "")


def domains_agree(repo: Path) -> Result:
    import importlib.util
    spec = importlib.util.spec_from_file_location("target_domains", repo / "scripts" / "domains.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["target_domains"] = module   # a dataclass resolves its module here
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return "fail", f"domains.py does not import: {exc}"
    listed = {name for name, _ in module.list_domains()}
    checked = set(module.DOMAIN_CHECKS)
    if listed != checked:
        return "fail", f"differ: {sorted(listed ^ checked)}"
    return "pass", f"{len(listed)} domains"


# --- remote checks ----------------------------------------------------------

def repo_view(repo: Path) -> dict:
    data = gh_json(repo, "repo", "view", "--json",
                   "description,repositoryTopics,visibility,nameWithOwner")
    return data if isinstance(data, dict) else {}


def description_ok(repo: Path) -> Result:
    if not has_remote(repo):
        return "fail", "no GitHub remote to read back from"
    data = repo_view(repo)
    if not data:
        return "fail", "could not read the repo back with `gh repo view`"
    text = (data.get("description") or "").strip()
    if not text:
        return "fail", "the GitHub description is empty"
    if "\n" in text:
        return "fail", "the description runs over one line"
    return "pass", f"read back: {text[:70]}"


def topics_ok(repo: Path) -> Result:
    if not has_remote(repo):
        return "fail", "no GitHub remote to read back from"
    data = repo_view(repo)
    topics = data.get("repositoryTopics") or []
    if not topics:
        return "fail", "no topics set; `gh repo edit --add-topic ...`"
    return "pass", f"{len(topics)} topic(s)"


def page_fetched(repo: Path) -> Result:
    if not has_remote(repo):
        return "fail", "no GitHub remote"
    data = repo_view(repo)
    if data.get("visibility") != "PUBLIC":
        return "na", "the repo is not public yet; check its page after the flip"
    slug = data.get("nameWithOwner", "")
    rendered = gh_json(repo, "api", f"repos/{slug}/readme")
    if not rendered:
        return "fail", "GitHub serves no README for the published page"
    return "pass", f"github.com/{slug} serves its README"


IMAGE_URL = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)|<img[^>]+src=[\"'](https?://[^\"']+)")


def images_ok(repo: Path) -> Result:
    urls = [a or b for a, b in IMAGE_URL.findall(readme(repo))]
    for url in urls:
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "repo-release"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    return "fail", f"{url} returned {resp.status}"
        except Exception as exc:
            return "fail", f"{url}: {exc}"
    return "pass", f"{len(urls)} remote image(s) return 200"


def ci_green(repo: Path) -> Result:
    if not workflows(repo):
        return "fail", "no CI to pass"
    sha = head(repo)
    runs = gh_json(repo, "run", "list", "--commit", sha, "--json", "conclusion,status,name")
    if runs is None:
        return "fail", "could not read CI runs with `gh run list`"
    if not runs:
        return "fail", f"no CI run for {sha[:7]}: push the commit and wait for CI"
    pending = [r["name"] for r in runs if r.get("status") != "completed"]
    if pending:
        return "fail", f"CI still running: {pending}"
    failed = [r["name"] for r in runs if r.get("conclusion") != "success"]
    if failed:
        return "fail", f"CI failed: {failed}"
    return "pass", f"{len(runs)} run(s) green on {sha[:7]}"


# --- the checklist ----------------------------------------------------------

def attest(item_id: str) -> Callable[[Path], Result]:
    return lambda repo: attested(repo, item_id)


BOTH = ("public", "release")
REL = ("release",)

ITEMS: list[Item] = [
    # publish-repo
    Item("publish-validator", "publish-repo", "Validator exits 0 on `--profile public`",
         BOTH, "auto", validator_ok("public")),
    Item("secrets-by-eye", "publish-repo",
         "Every configuration file read by eye for secrets, not just by scan",
         BOTH, "attest", attest("secrets-by-eye")),
    Item("destination-alive", "publish-repo", "Destination checked for signs of life",
         BOTH, "attest", attest("destination-alive")),
    Item("readme-lead", "publish-repo",
         "README leads with one sentence and an image, install before options",
         BOTH, "auto", readme_lead),
    Item("license", "publish-repo", "LICENSE present with real text", BOTH, "auto", license_ok),
    Item("description", "publish-repo",
         "Description is one line stating what it is, read back from the repo",
         BOTH, "remote", description_ok),
    Item("topics", "publish-repo", "Topics set, read back from the repo",
         BOTH, "remote", topics_ok),
    Item("counts", "publish-repo", "Every count the README states matches the tree",
         BOTH, "auto", counts_ok),
    Item("page-fetched", "publish-repo", "Published page fetched and checked",
         BOTH, "remote", page_fetched),
    Item("images-200", "publish-repo", "Every README image returns 200",
         BOTH, "remote", images_ok),
    Item("gaps-written", "publish-repo", "Open gaps written down",
         BOTH, "attest", attest("gaps-written")),
    # repo-hygiene
    Item("ignored-clean", "repo-hygiene",
         "`git ls-files -i -c --exclude-standard` prints nothing", BOTH, "auto", ignored_clean),
    Item("env-files", "repo-hygiene",
         "`.env` ignored and `.env.example` present and not ignored", BOTH, "auto", env_ignored),
    Item("no-build-output", "repo-hygiene", "No build output or dependency tree tracked",
         BOTH, "auto", no_build_output),
    Item("secrets-rotated", "repo-hygiene", "Any secret ever committed has been rotated",
         BOTH, "auto", history_secrets),
    Item("ci-shape", "repo-hygiene", "CI runs tests plus the tracked-yet-ignored gate",
         BOTH, "auto", ci_shape),
    Item("ci-green", "repo-hygiene", "Every CI gate passes on the current tree",
         BOTH, "remote", ci_green),
    Item("docs-indexed", "repo-hygiene",
         "`docs/` indexed once it holds more than three documents", BOTH, "auto", docs_indexed),
    # repo-versioning
    Item("bump-matches", "repo-versioning", "Bump matches the change against the public contract",
         REL, "attest", attest("bump-matches")),
    Item("changelog-reader", "repo-versioning",
         "Changelog entry is written for the person upgrading",
         REL, "attest", attest("changelog-reader")),
    Item("migration", "repo-versioning", "Any break names its migration step",
         REL, "auto", migration_named),
    Item("committed-together", "repo-versioning", "Version and changelog committed together",
         REL, "auto", committed_together),
    Item("tag-annotated", "repo-versioning", "Annotated tag matches the version string exactly",
         REL, "auto", tag_ok),
    Item("tag-shape", "repo-versioning", "Tag shape matches the repo's existing tags",
         REL, "auto", tag_shape),
    Item("release-validator", "repo-versioning", "`--profile release` exits 0",
         REL, "auto", validator_ok("release")),
    Item("unreleased", "repo-versioning", "`## [Unreleased]` section opened for the next change",
         REL, "auto", unreleased_open),
    # agent-native-repo, applies once AGENTS.md exists
    Item("guide-paths", "agent-native-repo", "No guide references a path outside the repo",
         BOTH, "auto", absolute_paths),
    Item("bridges", "agent-native-repo",
         "AGENTS.md is canonical, bridges are 5 lines and import it", BOTH, "auto", bridges_ok),
    Item("golden-rules", "agent-native-repo",
         "Golden rules name the damage, each pointing at a rule file", BOTH, "auto", golden_rules),
    Item("rules-index", "agent-native-repo", "Rules index covers every rule file",
         BOTH, "auto", rules_indexed),
    Item("rules-cite", "agent-native-repo",
         "Rules cite repo-relative paths, and the cited files exist", BOTH, "auto", cited_paths),
    Item("history-claims", "agent-native-repo", "Claims from history verified against current code",
         BOTH, "attest", attest("history-claims")),
    Item("env-example", "agent-native-repo",
         "`.env.example` covers every variable the source reads", BOTH, "auto", env_covered),
    Item("contributing-lead", "agent-native-repo",
         "CONTRIBUTING leads with the repo's most confusing thing",
         BOTH, "attest", attest("contributing-lead")),
    Item("agent-validator", "agent-native-repo", "Validator exits 0 on `--profile public`",
         BOTH, "auto", validator_ok("public")),
    # domain-gates, applies to a repo that builds domain gates
    Item("detector-marker", "domain-gates",
         "The detector names a file that cannot appear by accident",
         BOTH, "attest", attest("detector-marker")),
    Item("precedence", "domain-gates", "Precedence puts the most specific marker first",
         BOTH, "attest", attest("precedence")),
    Item("rule-failure", "domain-gates", "Every blocking rule names a concrete failure, not a preference",
         BOTH, "attest", attest("rule-failure")),
    Item("rule-source", "domain-gates", "The rule cites the maintained repo it came from",
         BOTH, "attest", attest("rule-source")),
    Item("checks-tested", "domain-gates", "Each check has a fixture test that fails without it",
         BOTH, "auto", checks_tested),
    Item("domains-agree", "domain-gates", "`list_domains` and `DOMAIN_CHECKS` name the same set",
         BOTH, "auto", domains_agree),
]


def applies(repo: Path, item: Item) -> str:
    """Return why an item does not apply, or an empty string when it does."""
    if item.skill == "agent-native-repo" and not (repo / "AGENTS.md").exists():
        return "no AGENTS.md: the repo is not agent-native"
    if item.skill == "domain-gates" and not (repo / "scripts" / "domains.py").exists():
        return "the repo builds no domain gates"
    if item.id == "contributing-lead" and not (repo / "CONTRIBUTING.md").exists():
        return "no CONTRIBUTING.md"
    return ""


def evaluate(repo: Path, profile: str) -> list[tuple[Item, str, str]]:
    rows = []
    for item in ITEMS:
        if profile not in item.profiles:
            continue
        reason = applies(repo, item)
        if reason:
            rows.append((item, "na", reason))
            continue
        try:
            status, detail = item.check(repo)
        except Exception as exc:  # a crashed check is a fail, never a pass
            status, detail = "fail", f"check crashed: {exc}"
        rows.append((item, status, detail))
    return rows


MARK = {"pass": "[x]", "fail": "[ ]", "attest": "[?]", "na": "[-]"}


def render(rows, profile: str) -> str:
    lines, skill = [], ""
    for item, status, detail in rows:
        if item.skill != skill:
            skill = item.skill
            lines.append(f"\n{skill}")
        note = f"  {detail}" if detail and status != "pass" else ""
        lines.append(f"  {MARK[status]} {item.id}: {item.text}{note}")
    open_items = [r for r in rows if r[1] in ("fail", "attest")]
    verdict = "PASS" if not open_items else f"BLOCKED: {len(open_items)} open item(s)"
    lines.append(f"\n{verdict} for profile {profile}")
    return "\n".join(lines).lstrip("\n")


def record(repo: Path, item_id: str, evidence: str) -> int:
    known = {i.id for i in ITEMS if i.kind == "attest"} | {"readme-lead", "secrets-rotated"}
    if item_id not in known:
        print(f"{item_id} is not an attestable item: {sorted(known)}", file=sys.stderr)
        return 2
    if len(evidence.strip()) < MIN_EVIDENCE:
        print(f"evidence must say what was checked, in at least {MIN_EVIDENCE} characters",
              file=sys.stderr)
        return 2
    path = attest_file(repo)
    if path is None:
        print("not a git repo", file=sys.stderr)
        return 2
    data = load_attestations(repo)
    data[item_id] = {"sha": head(repo), "evidence": evidence.strip(),
                     "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    print(f"attested {item_id} at {data[item_id]['sha'][:7]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="checklist", description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("action", nargs="?", default="check", choices=("check", "attest"))
    parser.add_argument("item", nargs="?", default="")
    parser.add_argument("--profile", choices=("public", "release"), default="release")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true", help="print every item, then exit")
    args = parser.parse_args(argv)

    if args.list:
        for item in ITEMS:
            print(f"{item.id:20} {item.kind:6} {','.join(item.profiles):14} {item.text}")
        return 0
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    if args.action == "attest":
        return record(repo, args.item, args.evidence)

    rows = evaluate(repo, args.profile)
    blocked = any(status in ("fail", "attest") for _, status, _ in rows)
    if args.json:
        print(json.dumps({"profile": args.profile, "ok": not blocked, "items": [
            {"id": i.id, "skill": i.skill, "kind": i.kind, "status": s, "detail": d}
            for i, s, d in rows]}, indent=2))
    else:
        print(render(rows, args.profile))
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
