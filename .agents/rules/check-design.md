# Check design

Every gate in this plugin is a function in `scripts/validate.py` returning a
list of findings. Three rules decide whether a finding blocks.

## The rule

**Block only on a defect the user can fix.** A missing LICENSE has a fix.
"README could be better" does not, and a block a reader cannot act on teaches
them to bypass the gate.

**Warn only with a written reason.** A warning blocks unless `KEEP_WARN` in
`scripts/validate.py` lists its code with the reason it cannot. A warning is
easy to skip, and a skipped convention is how a repo drifts. Add a code to
`KEEP_WARN` only when the finding is wrong for some repo types, or when no
repo change fixes it.

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

**Gate every checklist line.** Each `- [ ]` line under a skill's
`## Checklist` maps to one item in `scripts/checklist.py`, quoted verbatim.
`tests/test_checklist.py` fails on a line with no item and on an item whose line
changed. Pick the item's kind by who can decide it: code decides `auto`, GitHub
or the network decides `remote`, and only a reader decides `attest`. Prefer
`auto`. An `attest` item asks the agent for evidence, which is weaker than code.

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

## Escalation

**Conventions hold on every repo.** `escalate()` turns each warning into a
block in every profile, private repos included. A new `warn` finding therefore
blocks the day it ships, so give it a fix the user can make. `RELEASE_REQUIRED`
holds rules that guess, which block only at release. A pending bump keeps
`dirty-tree` and `tag-missing` as warnings, because the hook checks the version
edit before its commit and tag exist.

## README voice and structure

**The README states requirements, not a test rig.** `check_readme_voice` blocks a
model name, a `tested on` report and first person singular. It skips a line that
states a requirement, and it skips code. Both escapes exist because a hardware
requirement and a shell comment are correct content, and a gate that blocks
them gets switched off.

**The README shows its shape.** `check_readme_structure` asks for a diagram and
a tree map once a repo has two content directories. Below that, the layout is
the file list, so the finding warns.

This rule came from a private repo published with a README listing one laptop's
GPU and dated timings. The public profile never ran, because the create was
private. That is why every create, private included, runs the `public`
validator.

## Source

- `scripts/validate.py` — every check, and the `PROFILES` table that registers it
- `tests/test_validate.py` — the fixture-repo test for each check
