# Check design

Every gate in this plugin is a function in `scripts/validate.py` returning a
list of findings. Three rules decide whether a finding blocks.

## The rule

**Block only on a defect the user can fix.** A missing LICENSE has a fix.
"README could be better" does not, and a block a reader cannot act on teaches
them to bypass the gate.

**Warn when the repo's domain decides.** A CLI library has nothing to
screenshot. A config snippet has no version to tag. The check runs, the finding
shows, and the publish proceeds.

**Write the test first.** A check with no failing test is a check nobody has
seen work.

```python
def check_env_example(repo: Path) -> list[Finding]:
    ...
    if not sample.exists():
        return [Finding("block", "env-example-missing",
                        f"source reads {len(found)} environment variable(s) but there is "
                        "no .env.example listing them")]
```

## Why

**This has bitten before.** The first draft of `check_absolute_paths` matched
`~/` as a machine-local path. A README documenting that config lives at
`~/.app/config.toml` is correct and portable, so the draft blocked a good file.

The same draft used `LOCAL_PATH.search`, which reports one path per line. A line
naming two paths produced one finding, and the test asserting two failed. Both
were caught by tests written before the code was trusted, not by reading it.

`os.getenv` was missing from the first environment scan, which gave a clean
result on a repo that reads three variables through that exact form. A false
all-clear is worse than no check, because it is read as a pass.

## Source

- `scripts/validate.py` — every check, and the `PROFILES` table that registers it
- `tests/test_validate.py` — the fixture-repo test for each check
