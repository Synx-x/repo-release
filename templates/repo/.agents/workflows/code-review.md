---
description: Review a change for correctness and convention before it merges. Read-only.
---

# Code review

1. Read `AGENTS.md` golden rules. Any violation is a blocking finding.
2. Read the diff, not the file. A change is judged on what it changes.
3. Check the cited rule files for anything the diff touches.
4. Run the test suite. A review that did not run the tests is an opinion.
5. Report findings most severe first, each with the file and line.

## Checklist

- [ ] No golden rule broken
- [ ] Tests pass
- [ ] Changelog entry added if user-visible
- [ ] No secret, local path or build output in the diff
