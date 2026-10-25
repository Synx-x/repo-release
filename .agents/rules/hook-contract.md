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

**Give a one-shot escape, and give it only to the user.** The user types
`[publish-ok]` in a prompt. The `UserPromptSubmit` handler records it in the
approval store, and the next publish or version edit in that session consumes
it. `[publish-ok]` inside a tool call does nothing, because the agent writes
tool calls and would grant itself the exception.

**Refuse the calls that switch the gate off.** A write into the installed
plugin, a write to the approval store, and a settings change that sets
`REPO_RELEASE_MODE` or disables the plugin each exit 2. `off` mode does not lift
this guard. The source checkout stays editable, so the plugin can be developed.

**A crashed check is a fail.** Fail-open covers a crash of the hook itself. A
check inside `scripts/checklist.py` that raises reports `fail`, so a broken
check never reads as a pass.

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

**The agent escape bit too.** Up to 0.3.2 the escape was `[publish-ok]` in the
command, so the agent being gated could type it. On 2026-10-25 a session skipped
checklist steps and the user found the gaps by reading the files afterwards.
The gate checked files, not steps, and its one exception was in the agent's
hands. 0.4.0 moved the steps into `scripts/checklist.py` and the exception into
the user's prompt.

## Source

- `hooks/guard_publish.py` — triggers, mode resolution, approvals, tamper guard
- `scripts/checklist.py` — the checklist items the publish gate runs
- `hooks/hooks.json` — the matchers that wire it
