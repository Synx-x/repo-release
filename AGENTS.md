# AGENTS.md

Canonical project guide. `CLAUDE.md` and `GEMINI.md` are five-line bridges that
import this file. Edit conventions here.

## What this is

A Claude Code plugin holding the publish surface, repository hygiene and release
discipline for any repo. Four skills explain the why, `scripts/validate.py`
decides the whether, and `hooks/guard_publish.py` blocks the publish command
while a blocking finding stands.

## Repo map

| Path | Holds |
|---|---|
| `skills/` | Five skills: publish, hygiene, versioning, agent-native, domain-gates |
| `scripts/validate.py` | The checker. Two profiles, exit 1 on a blocking finding |
| `scripts/domains.py` | Classifies a repo by domain, then gates on that domain's needs |
| `scripts/scaffold.py` | Copies the template set into a repo, never overwriting |
| `hooks/guard_publish.py` | Runs the validator on publish and release commands |
| `templates/repo/` | Every file a published repo needs, with a comment on why |
| `templates/license/` | MIT and Apache-2.0 texts |
| `tests/` | Fixture-repo tests for the validator and the scaffolder |

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+, standard library only |
| Test | pytest |
| CI | GitHub Actions, 3.11 to 3.13 |

## Build and run

```bash
python3 -m pytest tests -q
python3 scripts/validate.py . --profile release
python3 scripts/scaffold.py /tmp/probe --dry-run
```

## Golden rules

1. **A check blocks only on a defect the user can fix.** A finding nobody can
   act on gets the whole gate switched off. See
   `.agents/rules/check-design.md`.
2. **Every check has a test that fails without it.** A check with no failing
   test is a check nobody has seen work. See `.agents/rules/check-design.md`.
3. **The hook fails open.** A broken gate must never strand the publish it
   guards. See `.agents/rules/hook-contract.md`.
4. **No absolute path in a skill or template.** This plugin exists to stop
   exactly that reaching a published repo. See
   `.agents/rules/check-design.md`.
5. **The scaffolder never overwrites.** A scaffold that clobbers a
   hand-written README gets run once and never trusted again. See
   `.agents/rules/hook-contract.md`.

## Rules index

| Working on… | Read |
|---|---|
| Adding or narrowing a check | `.agents/rules/check-design.md` |
| A domain detector or gate | `.agents/rules/check-design.md` |
| The hook, its modes, its escapes | `.agents/rules/hook-contract.md` |
| A skill body | `.agents/rules/check-design.md` |

## Coding style

Standard library only, no dependencies. Type hints on module-level functions.
A docstring opens with what the module is for, then notes anything a reader
would otherwise re-derive.
