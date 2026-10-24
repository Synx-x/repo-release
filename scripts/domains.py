#!/usr/bin/env python3
"""Classify a repository by domain, then check the artifacts that domain needs.

A single checklist for every repo either blocks too much or says too little.
A Rust crate needs `Cargo.lock` and a licence field. A npm library lives or
dies on the `files` and `exports` fields. A Claude Code plugin needs valid
`plugin.json` frontmatter, and an invalid one breaks installation rather than
merely looking wrong.

Detection is deterministic: a marker file decides the domain, in a fixed
precedence order. No model, no guessing, the same answer every run.

Every rule here came from inspecting a maintained exemplar and reading what it
actually ships. The `Source:` line on each check names the repo or the record.

    python3 validate.py . --domain auto      # detect, then gate
    python3 validate.py . --list-domains
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from validate import Finding, read, walk  # noqa: F401  (shared helpers)


# --- detection ------------------------------------------------------------

@dataclass(frozen=True)
class Marker:
    domain: str
    test: str          # human-readable, shown by --list-domains


# Precedence matters. A plugin repo often also has a package.json, and a
# monorepo also has manifests, so the most specific marker wins.
DETECTORS: list[tuple[str, object]] = [
    ("claude-plugin", lambda r: (r / ".claude-plugin").is_dir()),
    ("mcp-server", lambda r: (r / "server.json").exists()
        or _declares(r, "modelcontextprotocol")
        or _imports_mcp(r)),
    ("monorepo", lambda r: (r / "pnpm-workspace.yaml").exists()
        or (r / "turbo.json").exists() or _workspaces(r)),
    ("rust-crate", lambda r: (r / "Cargo.toml").exists()),
    ("node-library", lambda r: (r / "package.json").exists()),
    ("python-library", lambda r: (r / "pyproject.toml").exists()
        or (r / "setup.py").exists()),
    ("docs", lambda r: _mostly_markdown(r)),
    ("generic", lambda r: True),
]


def _declares(repo: Path, needle: str) -> bool:
    for name in ("package.json", "pyproject.toml", "go.mod"):
        path = repo / name
        if path.exists() and needle in read(path).lower():
            return True
    return False


def _imports_mcp(repo: Path) -> bool:
    """A server that speaks MCP without importing the SDK is still an MCP server.

    Three signals, strongest first: a marker file, an SDK import, then the
    method names only an MCP server answers. A hand-written JSON-RPC server has
    no dependency to find, and `initialize` plus `tools/call` is unambiguous.
    """
    import_pattern = re.compile(
        r"^\s*(?:from\s+mcp\b|import\s+mcp\b|from\s+@modelcontextprotocol/)",
        re.MULTILINE,
    )
    method_pattern = re.compile(r'["\']tools/call["\']|["\']initialize["\']')
    for path in walk(repo):
        if path.suffix not in (".py", ".ts", ".js"):
            continue
        if path.stat().st_size > 400_000:
            continue
        text = read(path)
        if import_pattern.search(text):
            return True
        if method_pattern.search(text) and "jsonrpc" in text:
            return True
    return False


def _workspaces(repo: Path) -> bool:
    package = repo / "package.json"
    if not package.exists():
        return False
    try:
        return bool(json.loads(read(package)).get("workspaces"))
    except json.JSONDecodeError:
        return False


def _mostly_markdown(repo: Path) -> bool:
    total = md = 0
    for path in walk(repo):
        total += 1
        if path.suffix.lower() in (".md", ".mdx", ".rst", ".txt"):
            md += 1
    return total > 0 and md / total > 0.7


def detect(repo: Path) -> str:
    for domain, test in DETECTORS:
        try:
            if test(repo):
                return domain
        except Exception:
            continue
    return "generic"


def list_domains() -> list[tuple[str, str]]:
    return [
        ("claude-plugin", "a .claude-plugin directory with plugin.json or marketplace.json"),
        ("mcp-server", "server.json, or a dependency on the modelcontextprotocol SDK"),
        ("monorepo", "pnpm-workspace.yaml, turbo.json, or a workspaces field"),
        ("rust-crate", "Cargo.toml"),
        ("node-library", "package.json"),
        ("python-library", "pyproject.toml or setup.py"),
        ("docs", "more than 70 percent markup files"),
        ("generic", "anything else"),
    ]


# --- shared helpers -------------------------------------------------------

def _json(repo: Path, relative: str) -> tuple[dict | None, str]:
    path = repo / relative
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(read(path)), ""
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _pyproject_value(repo: Path, pattern: str) -> str:
    path = repo / "pyproject.toml"
    if not path.exists():
        return ""
    match = re.search(pattern, read(path), re.MULTILINE)
    return match.group(1) if match else ""


# --- claude-plugin --------------------------------------------------------

SKILL_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _plugin_path_fields(repo: Path, data: dict) -> list[Finding]:
    """A declared path that resolves to nothing breaks the plugin's promise.

    Evidence: 91 of the 92 plugin manifests in wshobson/agents (41k stars)
    declare no path field at all, because the harness finds `skills/` and
    `commands/` by convention. The one that does declares five `skills` paths,
    and all five exist. anthropics/claude-plugins-official declares none.

    So a path field is a deliberate claim, not boilerplate, and a claim that
    points nowhere is the defect. This repo shipped `"commands": ["./commands/"]`
    for a directory that did not exist, which no field check could catch.
    """
    out: list[Finding] = []
    for field in ("skills", "commands", "agents"):
        declared = data.get(field)
        if not declared:
            continue
        entries = declared if isinstance(declared, list) else [declared]
        for entry in entries:
            if not isinstance(entry, str) or "://" in entry:
                continue
            target = (repo / entry).resolve()
            if not target.exists():
                out.append(Finding(
                    "block", "plugin-path-missing",
                    f"plugin.json declares {field} path {entry!r}, which does "
                    "not exist; the harness loads nothing from it",
                    ".claude-plugin/plugin.json"))
    return out


def check_claude_plugin(repo: Path) -> list[Finding]:
    """A plugin that fails here does not install, so these block.

    Evidence: anthropics/claude-plugins-official ships `name` and `description`
    only in a plugin manifest, and wshobson/agents gates CI on
    `python3 -m json.tool` over every marketplace.json, plugin.json and
    hooks.json, which is the same check this runs.
    """
    out: list[Finding] = []

    manifest = repo / ".claude-plugin" / "plugin.json"
    if manifest.exists():
        data, error = _json(repo, ".claude-plugin/plugin.json")
        if data is None:
            out.append(Finding("block", "plugin-json-invalid",
                               f"plugin.json does not parse: {error}",
                               ".claude-plugin/plugin.json"))
        else:
            for field in ("name", "description"):
                if not str(data.get(field) or "").strip():
                    out.append(Finding("block", "plugin-json-field",
                                       f"plugin.json has no {field}; the harness "
                                       "cannot list the plugin without it",
                                       ".claude-plugin/plugin.json"))
            if data.get("name") and "/" in str(data["name"]):
                out.append(Finding("block", "plugin-json-name",
                                   "plugin name contains a slash, which the "
                                   "installer rejects",
                                   ".claude-plugin/plugin.json"))
            out.extend(_plugin_path_fields(repo, data))

    market = repo / ".claude-plugin" / "marketplace.json"
    if market.exists():
        data, error = _json(repo, ".claude-plugin/marketplace.json")
        if data is None:
            out.append(Finding("block", "marketplace-json-invalid",
                               f"marketplace.json does not parse: {error}",
                               ".claude-plugin/marketplace.json"))
        else:
            for field in ("name", "owner", "plugins"):
                if not data.get(field):
                    out.append(Finding("block", "marketplace-json-field",
                                       f"marketplace.json has no {field}",
                                       ".claude-plugin/marketplace.json"))
            for index, entry in enumerate(data.get("plugins") or []):
                for field in ("name", "source", "description"):
                    if not entry.get(field):
                        out.append(Finding(
                            "block", "marketplace-entry",
                            f"plugins[{index}] has no {field}; the harness cannot "
                            "resolve the entry",
                            ".claude-plugin/marketplace.json"))

    hooks = repo / "hooks" / "hooks.json"
    if hooks.exists():
        if _json(repo, "hooks/hooks.json")[0] is None:
            out.append(Finding("block", "hooks-json-invalid",
                               "hooks.json does not parse, so no hook is registered",
                               "hooks/hooks.json"))

    skills = sorted(repo.rglob("SKILL.md"))
    for skill in skills:
        text = read(skill)
        front = SKILL_FRONTMATTER.search(text)
        rel = skill.relative_to(repo).as_posix()
        if front is None:
            out.append(Finding("block", "skill-frontmatter",
                               "no YAML frontmatter, so the skill is never loaded", rel))
            continue
        block = front.group(1)
        for field in ("name", "description"):
            if not re.search(rf"^{field}\s*:", block, re.MULTILINE):
                out.append(Finding("block", "skill-field",
                                   f"frontmatter has no {field}", rel))
        name = re.search(r"^name\s*:\s*(\S+)", block, re.MULTILINE)
        if name and skill.parent.name != name.group(1):
            out.append(Finding("warn", "skill-name-mismatch",
                               f"frontmatter name {name.group(1)!r} differs from "
                               f"directory {skill.parent.name!r}", rel))
        if len(text) > 8000:
            out.append(Finding("warn", "skill-long",
                               f"{len(text)} bytes; a skill body over 8 KB loads "
                               "slowly into context", rel))

    if not skills and (repo / ".claude-plugin").is_dir():
        out.append(Finding("warn", "skill-missing",
                           "no SKILL.md anywhere; a plugin with no skill, command "
                           "or agent adds nothing"))
    if not out:
        out.append(Finding("note", "claude-plugin-ok",
                           f"manifests parse, {len(skills)} skill(s) have frontmatter"))
    return out


# --- mcp-server -----------------------------------------------------------

MCP_MARKERS = ("server.json", "smithery.yaml", "glama.json")
TRANSPORTS = ("stdio", "http", "sse")


def check_mcp_server(repo: Path) -> list[Finding]:
    """An MCP server is judged on discoverability and transport documentation.

    Evidence: github/github-mcp-server ships server.json plus a Dockerfile,
    firecrawl ships server.json, smithery.yaml and glama.json, and notion ships
    a Dockerfile and a RELEASING.md. All three document the transport in the
    README, because a client cannot connect without knowing it.
    """
    out: list[Finding] = []
    readme = read(repo / "README.md").lower()

    # Word boundaries matter. `sse` matches inside "accessible", and prose
    # about accessibility once satisfied this check on a README that named no
    # transport at all.
    if not any(re.search(rf"\b{name}\b", readme) for name in TRANSPORTS):
        out.append(Finding("warn", "mcp-transport-undocumented",
                           "README names no transport; a client cannot connect "
                           "without knowing whether it is stdio, http or sse",
                           "README.md"))

    if not any((repo / name).exists() for name in MCP_MARKERS):
        out.append(Finding("warn", "mcp-registry-missing",
                           "no server.json, smithery.yaml or glama.json; the server "
                           "will not appear in a registry"))

    server, error = _json(repo, "server.json")
    if server is not None:
        for field in ("name", "version", "description"):
            if not server.get(field):
                out.append(Finding("warn", "mcp-server-json-field",
                                   f"server.json has no {field}", "server.json"))

    if not (repo / "Dockerfile").exists():
        out.append(Finding("note", "mcp-docker",
                           "no Dockerfile; optional, but every high-star MCP server "
                           "ships one"))
    out.append(Finding("note", "mcp-ok", "MCP artifact set checked"))
    return out


# --- language domains -----------------------------------------------------

def check_python_library(repo: Path) -> list[Finding]:
    """A published Python package is judged on what the index reads.

    Evidence: pydantic ships `HISTORY.md`, `CITATION.cff`, `Makefile` and a
    release script. A typed package ships `py.typed` or the annotations are
    invisible to every consumer's type checker.
    """
    out: list[Finding] = []
    if not _pyproject_value(repo, r'^\s*requires-python\s*=\s*["\']([^"\']+)'):
        out.append(Finding("warn", "python-no-requires",
                           "no requires-python; pip installs it on every version",
                           "pyproject.toml"))
    if not (repo / "tests").is_dir():
        out.append(Finding("warn", "python-no-tests", "no tests directory"))
    annotations = any("->" in read(p) for p in repo.rglob("*.py") if p.stat().st_size < 200000)
    py_typed = any(p.name == "py.typed" for p in repo.rglob("py.typed"))
    if annotations and not py_typed:
        out.append(Finding("warn", "python-not-typed-marker",
                           "source carries annotations but no py.typed, so a "
                           "consumer's type checker ignores them"))
    if not out:
        out.append(Finding("note", "python-ok", "packaging metadata checked"))
    return out


BIN_HINT = re.compile(r"^\[project\.scripts\]|^\s*\"bin\"\s*:|^\[\[bin\]\]", re.MULTILINE)


def check_cli_tool(repo: Path) -> list[Finding]:
    """A CLI's first screen is install plus usage.

    Evidence: sharkdp/bat and clap-rs/clap both lead with install, then an
    examples section, and both ship shell completions or a man page generator.
    """
    out: list[Finding] = []
    declared = BIN_HINT.search(read(repo / "pyproject.toml")) or \
        BIN_HINT.search(read(repo / "package.json")) or \
        BIN_HINT.search(read(repo / "Cargo.toml"))
    if not declared:
        out.append(Finding("warn", "cli-no-entrypoint",
                           "no console script or bin entry; the tool cannot be "
                           "installed as a command"))
    readme = read(repo / "README.md").lower()
    if "usage" not in readme and "```" not in readme:
        out.append(Finding("warn", "cli-no-usage",
                           "README shows no example invocation", "README.md"))
    return out


def check_rust_crate(repo: Path) -> list[Finding]:
    """Evidence: bat and clap ship Cargo.lock, a licence field, SECURITY.md and
    a CHANGELOG.md. A crate published to crates.io without a licence field is
    rejected outright."""
    out: list[Finding] = []
    manifest = read(repo / "Cargo.toml")
    if not re.search(r"^\s*license(-file)?\s*=", manifest, re.MULTILINE):
        out.append(Finding("block", "rust-no-license-field",
                           "Cargo.toml has no license or license-file field; "
                           "crates.io rejects the publish",
                           "Cargo.toml"))
    if not (repo / "Cargo.lock").exists():
        out.append(Finding("warn", "rust-no-lock",
                           "no Cargo.lock; a binary crate needs one for a "
                           "reproducible build", "Cargo.lock"))
    if not (repo / "SECURITY.md").exists():
        out.append(Finding("warn", "security-md-missing",
                           "no SECURITY.md; a published crate needs a reporting "
                           "route", "SECURITY.md"))
    return out


def check_node_library(repo: Path) -> list[Finding]:
    """Evidence: sindresorhus/got sets `files: ["dist/source"]`, a conditional
    `exports` map, `engines.node`, and `type: module`. Without `files`, the
    published tarball includes tests, sources and config."""
    out: list[Finding] = []
    data, error = _json(repo, "package.json")
    if data is None:
        return [Finding("warn", "package-json-invalid", f"package.json does not parse: {error}")]
    if not data.get("files"):
        out.append(Finding("warn", "npm-no-files-field",
                           "no files field; the published tarball includes tests, "
                           "sources and config", "package.json"))
    if not data.get("exports"):
        out.append(Finding("warn", "npm-no-exports",
                           "no exports map; deep imports stay public API forever",
                           "package.json"))
    if not data.get("engines"):
        out.append(Finding("warn", "npm-no-engines",
                           "no engines field; the package installs on a runtime it "
                           "was never tested on", "package.json"))
    if data.get("private") is True:
        out.append(Finding("note", "npm-private",
                           "marked private, so the publishing checks matter less"))
    return out


def check_monorepo(repo: Path) -> list[Finding]:
    out: list[Finding] = []
    workflows = list((repo / ".github" / "workflows").glob("*.yml")) \
        if (repo / ".github" / "workflows").is_dir() else []
    if not workflows:
        out.append(Finding("warn", "monorepo-no-ci",
                           "no CI workflow; a monorepo without one drifts per package"))
    if not (repo / "CODEOWNERS").exists() and \
            not (repo / ".github" / "CODEOWNERS").exists():
        out.append(Finding("note", "monorepo-no-codeowners",
                           "no CODEOWNERS; optional at small size"))
    return out


def check_docs(repo: Path) -> list[Finding]:
    out: list[Finding] = []
    if not (repo / "README.md").exists():
        out.append(Finding("block", "docs-no-index",
                           "a docs repo with no README has no entry point"))
    return out


DOMAIN_CHECKS = {
    "claude-plugin": check_claude_plugin,
    "mcp-server": check_mcp_server,
    "python-library": check_python_library,
    "rust-crate": check_rust_crate,
    "node-library": check_node_library,
    "monorepo": check_monorepo,
    "docs": check_docs,
    "generic": lambda repo: [Finding("note", "generic", "no domain gate applied")],
}


def check_domain(repo: Path, domain: str = "auto") -> tuple[str, list[Finding]]:
    """Detect when asked, then run that domain's gate."""
    resolved = detect(repo) if domain == "auto" else domain
    check = DOMAIN_CHECKS.get(resolved)
    if check is None:
        return resolved, [Finding("warn", "domain-unknown",
                                  f"no gate for domain {resolved!r}")]
    return resolved, check(repo)
