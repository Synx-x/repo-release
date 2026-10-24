# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] - 2026-10-24

### Added

- `check_claimed_counts`, warning. A README table row stating `| Hooks | 72 |`
  is a checkable claim, and nothing checked it before. harness-kit claimed 72
  hooks, 39 subagents, 11 skills and 891 tests against 105, 40, 19 and 2533 in
  the tree. Only a table row is read, because a number in prose is ambiguous and
  a gate that guesses at it cries wolf.
- The `publish-repo` skill now sets and reads back the GitHub About and topics.
  They live on GitHub, so no local check reaches them, and `harness-kit` was
  published with neither while reporting nothing.

## [0.3.1] - 2026-10-24

### Fixed

- A plugin with no `.env.example` no longer blocks. A plugin's variables are
  behaviour toggles rather than setup values, and a `.env` file cannot say what
  a toggle does. A plugin is now judged on whether its docs name the variables,
  and an undocumented one warns. A non-plugin still blocks, because a service
  really does need the file. Found by running the gate on `harness-kit`, which
  reads 150 variables and ships no sample.

## [0.3.0] - 2026-10-24

### Added

- `check_readme_images`, blocking. A README that embeds a local image missing
  from the repo renders a broken image on the published page. Remote images are
  not fetched, so the gate stays offline.
- `check_conformance`, warning only. Five conventions measured across 20
  top-starred repos on 2026-10-24: a security reporting route, a CI workflow, a
  dependency-update config, `.gitattributes`, and a `CONTRIBUTING.md`. Each
  finding states its measured ratio.
- The `publish-repo` skill now runs its own gate on a second, unrelated repo
  before trusting a new check. Every check here was written against this tree,
  and this tree passed all of them.

### Fixed

- The `mcp-server` transport check matched `sse` inside "accessible", so prose
  about accessibility satisfied it on a README that named no transport.

### Changed

- `.gitattributes`, `SECURITY.md` and `.github/dependabot.yml` added, because
  the new conformance checks fired on this repo.

## [0.2.2] - 2026-10-24

### Fixed

- The MCP transport check matched its tokens as substrings, so `sse` matched
  inside "accessible". A README about OCR passed the check while naming no
  transport. The tokens now match on word boundaries.

## [0.2.1] - 2026-10-24

### Added

- Four slash commands: `/repo-release:publish`, `/repo-release:hygiene`,
  `/repo-release:version` and `/repo-release:agent`. Each routes to one skill
  and runs the validator before touching the repo.
- A `plugin-path-missing` check, blocking. When `plugin.json` declares a
  `skills`, `commands` or `agents` path that does not exist, the harness loads
  nothing from it.

### Fixed

- `plugin.json` declared `"commands": ["./commands/"]` for a directory that did
  not exist. Every field check passed, because the field was present and
  well-formed. Only the path was wrong, and this gate did not look at paths.
- The README listed four slash commands under names the plugin never shipped,
  claimed four skills where five exist, and said the hook had never run against
  a real publish. All three were false.

## [0.2.0] - 2026-10-24

### Added

- Domain classification in `scripts/domains.py`. `--domain auto` detects the
  repo type from marker files in a fixed precedence order, then applies that
  type's gate. `--list-domains` prints the set.
- Eight domain gates: `claude-plugin`, `mcp-server`, `monorepo`, `rust-crate`,
  `node-library`, `python-library`, `docs`, `generic`.
- The `domain-gates` skill, recording which maintained repo each rule was
  measured on.

### Changed

- The hook runs `--domain auto` on every publish and release, so a plugin with
  an invalid manifest is refused before it can be installed by anyone.

## [0.1.1] - 2026-10-24

### Fixed

- A version bump now checks the version being written rather than the one on
  disk. Before, every bump passed, because the check read the release it was
  replacing.
- `plugin.json` counts as a version source, in both the validator and the hook.
  This plugin's own manifest was unguarded.

## [0.1.0] - 2026-10-24

### Added

- `validate.py`, checking a repo against the publish surface on `--profile
  public` and against version, changelog and tag coherence on `--profile
  release`. Exits 1 on a blocking finding.
- `scaffold.py`, copying the full template set into a repo without overwriting
  an existing file.
- Four skills: `publish-repo`, `repo-hygiene`, `repo-versioning` and
  `agent-native-repo`.
- `guard_publish.py`, refusing a publish or a release while a blocking finding
  stands. Fails open, and honours `[publish-ok]` and `[release-ok]` as logged
  one-shot escapes.
- Template set: README, AGENTS.md with CLAUDE.md and GEMINI.md bridges,
  CHANGELOG, CONTRIBUTING, SECURITY, `.env.example`, `.gitignore`, a CI
  workflow, and an example rule and workflow.
- MIT and Apache-2.0 license texts.

[Unreleased]: https://github.com/Synx-x/repo-release/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Synx-x/repo-release/releases/tag/v0.2.0
[0.1.1]: https://github.com/Synx-x/repo-release/releases/tag/v0.1.1
[0.1.0]: https://github.com/Synx-x/repo-release/releases/tag/v0.1.0
