# Hook contract

`hooks/guard_publish.py` runs the validator before a publish or a release.

## The rule

**Fail open.** Any exception inside the hook allows the call. A gate raises
`SystemExit` only on a deliberate finding. Everything else returns 0.

```python
    except SystemExit:
        raise
    except Exception:
        return 0
```

**Default to strict.** Unlike a warn-first guard, this one blocks by default
because the validator exits 0 on a clean tree. A guard that only warns on a
check that already discriminates is a guard nobody reads.

**Give a one-shot escape and log it.** `[publish-ok]` in a command and
`[release-ok]` in a version edit each allow exactly one call.

## Modes

| Setting | Result |
|---|---|
| `off` | the hook exits immediately |
| `warn` | finds and reports, allows the call |
| `strict` | exit 2, call refused |

`REPO_RELEASE_MODE` wins over `hooks.repo_release.mode` in the plugin config.

## Why

**This has bitten before.** A hook that blocks on its own bug strands the
exact action the user is trying to take, usually at the end of a long session.
Failing open costs a missed check. Failing closed costs the session.

The escape hatch exists for the same reason. A guard with no escape gets
disabled wholesale the first time it is wrong.

## Source

- `hooks/guard_publish.py` — triggers, mode resolution, escapes
- `hooks/hooks.json` — the matchers that wire it
