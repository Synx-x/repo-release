# AGENTS.md

Canonical project guide. Every AI tool reads this file, and every other tool
file in the repo is a five-line bridge that imports it. Edit conventions here,
never in a bridge.

Target length is 120 to 150 lines. Detail lives in `.agents/rules/` and is read
on demand through the rules index at the bottom.

## What this is

<One paragraph. What the project does, who it serves, and the one thing a
reader must understand before touching the code.>

## Repo map

| Path | Holds |
|---|---|
| `src/` | <the product code> |
| `tests/` | <tests, mirroring the source layout> |
| `docs/` | <narrative documents, indexed in docs/README.md> |
| `.agents/rules/` | <conventions, read on demand> |
| `scripts/` | <development scripts that are not part of the product> |

## Stack

| Layer | Choice |
|---|---|
| Language | <language and version> |
| Runtime | <runtime, pinned where> |
| Test | <framework> |
| CI | GitHub Actions |

## Build and run

```bash
<install>
<test>
<run>
```

## Environment

Every variable is documented in `.env.example`, with what it does and how to
generate it. <Name the ones that fail closed.>

## Branching

Branch from `<default branch>`. One concern per branch. <Commit message shape,
and why.>

## Golden rules

<!-- Each rule names the damage it prevents and points at the file that explains
     it. Aim for 8 to 12. If you cannot name the damage, it is not golden, so
     it belongs in a rule file rather than here. -->

1. **<Imperative rule>.** <One line naming what breaks when it is broken.>
   See `.agents/rules/<file>.md`.
2. **<Imperative rule>.** <The damage.> See `.agents/rules/<file>.md`.
3. **<Imperative rule>.** <The damage.> See `.agents/rules/<file>.md`.

## Rules index

| Working on… | Read |
|---|---|
| <area> | `.agents/rules/<file>.md` |
| <area> | `.agents/rules/<file>.md` |
| <area> | `.agents/workflows/<file>.md` |

## Coding style

<The two or three things a diff will be rejected for. Not a full style guide,
because nobody reads one. Point at the formatter for everything mechanical.>

## Adding things

<!-- Name the steps for the addition a contributor is most likely to attempt.
     Dependency, endpoint, migration, whatever the repo's real unit of change
     is. -->

- **<A new dependency>**: <the steps>
- **<A new endpoint>**: <the steps>

## Tooling

<Which AI tools are configured for this repo, and where each one's entry point
lives. The bridges import this file, so nothing else needs listing.>
