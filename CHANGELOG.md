# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Synx-x/repo-release/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Synx-x/repo-release/releases/tag/v0.1.1
[0.1.0]: https://github.com/Synx-x/repo-release/releases/tag/v0.1.0
