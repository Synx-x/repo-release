---
description: Set the version, write the changelog entry and cut the tag so all three agree.
argument-hint: "patch | minor | major | <version>"
---

Read the `repo-versioning` skill, then run the release against the current repository.

The argument picks the next version. `patch`, `minor` and `major` bump from the version on disk. An explicit number such as `0.3.0` is taken as given.

Read the version and the changelog first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile release --domain auto
```

Write the changelog entry before the tag. A tag with no readable entry is a number rather than a release. Put the entry under a new `## [<version>] - <date>` heading. Then bump the manifest, then rerun the validator to confirm the three agree.

Cut the tag with `git tag -a v<version> -m "<summary>"`. Do not push it. The hook runs the release profile on `git push --tags`, so a pushed tag is the point of no return.
