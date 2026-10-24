# Contributing

Setup is two commands and no virtualenv. Tests run on the system interpreter.

## Setup

```bash
git clone https://github.com/Synx-x/repo-release
cd repo-release
```

Nothing to install. Both scripts use only the Python standard library, and the
hook runs on whatever `python3` resolves to.

## Verify

```bash
python3 -m pytest tests -q
```

The suite covers the validator and the scaffolder. Each test builds a throwaway
repo holding exactly the defect under test, so a passing run means the checks
discriminate rather than that the fixtures are empty.

If `python3` cannot import `pytest`, point the command at an interpreter that
has it:

```bash
/path/to/python -m pytest tests -q
```

## Trying the validator by hand

```bash
mkdir -p /tmp/probe && cd /tmp/probe && git init -q
python3 /path/to/repo-release/scripts/validate.py . --profile public
```

A bare repo should report missing README and LICENSE. Then scaffold into it and
run again, which should come back clean apart from the unfilled placeholders.

## Branching

Branch from `main`. One concern per branch. Commit messages take a `type: what
changed` shape, matching the changelog categories: `add`, `fix`, `docs`,
`hygiene`, `release`.

## Before opening a pull request

- [ ] `python3 -m pytest tests -q` passes
- [ ] A new check has a test that fails without it
- [ ] `## [Unreleased]` has an entry, if the change is visible to a user
- [ ] `scripts/validate.py . --profile public` still exits 0

## Adding a check

A check is a function in `scripts/validate.py` taking a `Path` and returning
`list[Finding]`. Register it in `PROFILES` for the profiles it belongs to.

Three rules for a new check:

- **Block only on a defect that has a fix.** A finding a user cannot act on
  gets the whole gate switched off.
- **Warning, not block, when the repo's domain decides.** A CLI library has
  nothing to screenshot. A config snippet has no version to tag.
- **Write the test first.** The test that fails without the check is the only
  evidence the check does anything.
