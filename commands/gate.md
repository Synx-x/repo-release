---
description: Run the full publish checklist against a repository and close every open item.
argument-hint: "[path] [public | release]"
---

Run the checklist the publish hook will run, then close what it reports. The target is the path given, or the current directory when none is given. The profile is `release` unless `public` is given.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" "${1:-.}" --profile "${2:-release}"
```

Each line is one step a skill names. `[x]` holds, `[ ]` fails, `[?]` needs a reader's judgement, `[-]` does not apply to this repo.

Close a `[ ]` item by fixing the repo, then rerun. Close a `[?]` item only after you have done the check it names. Then record what you found against the current commit:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" "${1:-.}" attest <item-id> --evidence "<what you checked and what you found>"
```

Commit before you attest. A new commit voids every attestation.

Do not ask the user for `[publish-ok]` to get past an open item. That approval is for a check that is wrong about this repo, and only the user grants it.
