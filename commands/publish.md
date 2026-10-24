---
description: Take this repository from working to publicly readable, with the validator gating the publish.
argument-hint: "[path] [--dry-run]"
---

Read the `publish-repo` skill, then run it against the target repository. The target is the path given, or the current directory when none is given.

Start by running the validator, so the audit faces the same checks the hook will apply:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" "${1:-.}" --profile public --domain auto
```

Work the blocking findings first, then the warnings. Show the validation output before and after your changes, so the reader can see the repo move from failing to clean.

Do not run the publish command yourself. Stop before `gh repo create --public`, report what remains, and wait. The hook refuses that command while a blocking finding stands, so an early publish fails anyway.

With `--dry-run`, produce the artifact set and the audit report without writing files.
