---
name: repo-versioning
description: >
  Choose a version, write the changelog entry, and cut the tag so all three
  agree. Use when releasing, bumping a version, tagging, writing a CHANGELOG,
  deciding whether a change is major or minor, or when the user says "release
  this", "bump the version", or "tag it". Skip for repos that ship no version,
  and for uncommitted work that is not going out.
---

# Version, changelog, tag

A release is three artefacts that must name the same thing: the version string
in the manifest, the section in the changelog, and the tag on the commit. Two
of three agreeing is a release nobody can trust. The validator checks all
three, and `scripts/validate.py --profile release` is the gate.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile release
```

## 1. Choose the number

Semantic versioning, on the public contract only. A change to internals that no
caller can observe is a patch, however large the diff.

| Change | Bump | Example |
|---|---|---|
| A caller's code must change | major | 1.4.2 → 2.0.0 |
| New capability, old calls still work | minor | 1.4.2 → 1.5.0 |
| Fix or internal change, contract unchanged | patch | 1.4.2 → 1.4.3 |

Two calls that are yours to make, and both should be said out loud:

- **Before 1.0.0.** Everything is formally unstable, so the strict reading says
  every change is a major. That produces 0.9.0, 0.10.0, 0.11.0 for unrelated
  work and reads as noise. Use minor for a break and patch for a fix, and say
  the contract is not yet frozen in the README.
- **A dependency's break.** If an upstream removes something you re-export, the
  caller breaks, so it is major here too.

## 2. Write the changelog entry

Keep a Changelog shape, newest version first. The entry answers "what changes
for me", not "what did the author touch".

```markdown
## [1.5.0] - 2026-10-24

### Added
- `webbridge users` scaffolds one process per account, each with its own port
  and token.

### Changed
- The `--driver` flag accepts `g4f`. An unknown value now exits 2 instead of
  silently falling back to the browser driver.

### Fixed
- A one-turn tool request no longer lands in a stale conversation handle.

### Security
- Upstream errors return a reference. Ports, URLs and paths stay in the log.
```

Rules that keep it useful:

- **Write it for the person upgrading**, who has never seen the diff.
- **Name the break explicitly** under `Changed` or `Removed`, with the migration
  step. "Breaking" alone tells them nothing to do.
- **Link the issue or PR** when one exists.
- **Do not restate the commit log.** Ten entries of "refactor module" is a
  changelog that gets ignored.

## 3. Commit, tag, push

```bash
# manifest version and changelog committed together, so the tag points at both
git add pyproject.toml CHANGELOG.md
git commit -m "release: 1.5.0"
git tag -a v1.5.0 -m "1.5.0"
git push origin HEAD --follow-tags
```

An annotated tag (`-a`) carries a date, a tagger and a message. A lightweight
tag carries only a pointer, and most tools show it as anonymous.

The `v` prefix is a convention, not a requirement. It matters only that every
tag uses the same shape, because scripts and release tooling match on it.

## 4. Verify the release cut

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile release
git tag --list "v*" --sort=-v:refname | head -3
git log --oneline -1
```

The validator confirms the manifest, changelog and tag all name the same
version. If the tag exists but the changelog does not mention it, the release
is a bare tag: a number with no account of what changed.

## 5. After the tag

- **Publish the artefact**, if the repo ships one. A tag with nothing pushed to
  the index is a release only in git.
- **Add the next changelog section**, `## [Unreleased]`, so the next change has
  somewhere to land.
- **Say what the release does not cover.** A known gap named is a gap a reader
  trusts you about.

## Checklist

- [ ] Bump matches the change against the public contract
- [ ] Changelog entry is written for the person upgrading
- [ ] Any break names its migration step
- [ ] Version and changelog committed together
- [ ] Annotated tag matches the version string exactly
- [ ] Tag shape matches the repo's existing tags
- [ ] `--profile release` exits 0
- [ ] `## [Unreleased]` section opened for the next change
