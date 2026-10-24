---
description: Clean the ignore rules, tracked build output and CI gates in this repository.
argument-hint: "[path]"
---

Read the `repo-hygiene` skill, then run it against the target repository. The target is the path given, or the current directory when none is given.

Measure the state before changing anything:

```bash
git -C "${1:-.}" ls-files | head -50
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" "${1:-.}" --profile public --domain auto
```

Report what is tracked that should not be, then propose the ignore rules and the removal.

Tracked-file removal splits by reversibility. An ignore rule and an untrack are reversible, so apply them. A history rewrite is not reversible, so state the consequence and wait for approval before doing it.
