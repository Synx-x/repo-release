---
description: Write AGENTS.md as the canonical guide, with thin bridges for each tool and rules that cite real code.
argument-hint: "[path]"
---

Read the `agent-native-repo` skill, then run it against the target repository. The target is the path given, or the current directory when none is given.

Read what the repo already documents before writing anything:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" "${1:-.}" --profile public --domain auto
```

Two rules govern the output. Every path cited must exist, and every convention named must show the code it describes. A guide that cites a missing file sends the next reader nowhere.

`AGENTS.md` carries the content. `CLAUDE.md` and `GEMINI.md` are short bridges that point at it, never copies, because a copy drifts within a week.
