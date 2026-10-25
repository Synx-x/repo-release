# Release

The steps that cut a release of this plugin. The publish hook enforces each one,
so a skipped step blocks the tag push rather than shipping.

1. Write the `## [x.y.z] - YYYY-MM-DD` entry in `CHANGELOG.md` and bump
   `.claude-plugin/plugin.json`. Commit both together.
2. Push `main` and wait for CI to pass on that commit.
3. Run `python3 scripts/checklist.py . --profile release`. Close every `[ ]`
   item, then do each `[?]` check and record it with `attest`.
4. Tag with `git tag -a vx.y.z -m "..."` at the commit CI passed on.
5. Push the tag, then `gh release create vx.y.z --verify-tag` with the changelog
   entry as notes.
6. Run `claude plugin marketplace update repo-release` and
   `claude plugin update repo-release@repo-release`, then restart Claude Code.
