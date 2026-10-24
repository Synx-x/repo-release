---
name: domain-gates
description: >
  Understand or extend the classifier that decides what a repo needs based on
  what kind of repo it is. Use when a gate blocks on a rule that does not apply
  to this project, when adding support for a new repo type, or when the user
  asks what a plugin, MCP server, library or monorepo repo should ship. Skip for
  a one-off check on a repo whose type is already obvious.
---

# Domain gates

A repo's needs follow its type. A Rust crate without a `license` field is
rejected by crates.io. An npm library without `files` publishes its tests. A
Claude Code plugin with invalid `plugin.json` does not install at all.

So the validator classifies the type first, then applies what that type needs.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile public --domain auto
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --list-domains
```

## The classes

Detection reads marker files in a fixed precedence order. The most specific
marker wins, because a plugin repo often also carries a language manifest.

| Domain | Marker | Precedence |
|---|---|---|
| `claude-plugin` | a `.claude-plugin` directory | 1 |
| `mcp-server` | `server.json`, an MCP SDK dependency, or `initialize` + `tools/call` over JSON-RPC | 2 |
| `monorepo` | `pnpm-workspace.yaml`, `turbo.json`, or a `workspaces` field | 3 |
| `rust-crate` | `Cargo.toml` | 4 |
| `node-library` | `package.json` | 5 |
| `python-library` | `pyproject.toml` or `setup.py` | 6 |
| `docs` | more than 70 percent markup files | 7 |
| `generic` | anything else | 8 |

`--domain <name>` forces a class. Use it when detection is wrong, and fix the
detector rather than forcing it every run.

## What each class adds

**claude-plugin**, all blocking, because a failure here breaks installation:
`plugin.json` parses and carries `name` and `description`. `marketplace.json`
parses and every entry carries `name`, `source` and `description`. Every
`SKILL.md` has frontmatter with both fields. `hooks.json` parses.

Measured on `anthropics/claude-plugins-official` (56k stars): its plugin
manifests carry exactly `name`, `description` and `author`. Measured on
`wshobson/agents` (41k stars): CI runs `python3 -m json.tool` over
`marketplace.json`, every `plugin.json` and every `hooks.json`, which is the
same validity gate this applies.

**mcp-server**, warning, because a client can still connect by hand: the README
names a transport, and a registry file exists. Measured across
`github/github-mcp-server`, `firecrawl/firecrawl-mcp-server` and
`makenotion/notion-mcp-server`: all three ship `server.json`, a `Dockerfile`,
and a README that names stdio or http.

**rust-crate**, blocking on the licence field, because crates.io rejects a
publish without it. Measured on `sharkdp/bat` and `clap-rs/clap`: both ship
`Cargo.lock`, a licence field, `SECURITY.md` and `CHANGELOG.md`.

**node-library**, warning: `files`, `exports` and `engines`. Measured on
`sindresorhus/got`: `files: ["dist/source"]`, a conditional `exports` map,
`engines.node`, and `type: module`. Without `files`, the published tarball
carries tests and config.

**python-library**, warning: `requires-python`, a tests directory, and a
`py.typed` marker when the source carries annotations. Without the marker, every
consumer's type checker ignores those annotations.

**monorepo**, warning: a CI workflow, and `CODEOWNERS` as a note.

## Adding a class

1. Add the detector to `DETECTORS` in `scripts/domains.py`, at the precedence
   position its specificity deserves.
2. Write the check as a function taking a `Path` and returning `list[Finding]`.
3. Register it in `DOMAIN_CHECKS` and in `list_domains`.
4. Write the fixture test first.

**A rule measured on a maintained repo beats a rule reasoned from instinct.**
Every rule above names the repo it came from. An invented rule blocks a repo
doing the right thing for a reason the rule never imagined.

**Block only where the failure is a broken install or a rejected publish.**
Everything else warns. `plugin.json` blocks. A missing `Dockerfile` does not.

## Checklist

- [ ] The detector names a file that cannot appear by accident
- [ ] Precedence puts the most specific marker first
- [ ] Every blocking rule names a concrete failure, not a preference
- [ ] The rule cites the maintained repo it came from
- [ ] Each check has a fixture test that fails without it
- [ ] `list_domains` and `DOMAIN_CHECKS` name the same set
