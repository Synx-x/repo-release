---
name: repo-hygiene
description: >
  Keep a repository clean enough that a stranger can work in it and a build can
  be reproduced. Use when ignoring files, removing build output from history,
  fixing a repo that tracked its venv, setting up a CI gate, or when the user
  says the repo is messy, bloated or leaking. Skip during initial publish
  unless the validator flags something.
---

# Repository hygiene

Hygiene is the set of things nobody notices when right and everyone hits when
wrong. The reader is not the author. They have a different machine, a different
Python, and no `.venv` that already worked.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile public --quiet
```

## 1. Ignore advice before ignore debugging

A file is committed before the rule existed. Adding the rule does not untrack
it, because `.gitignore` governs untracked files only.

```bash
git ls-files -i -c --exclude-standard    # tracked, yet ignored: the real state
```

That command is the check the validator runs. Empty is correct.

## 2. Keep the ignore file honest

The set worth covering in nearly every repo:

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
dist/
build/

.env
.env.*
!.env.example
*.pem
*.key

.DS_Store
.idea/
.vscode/

node_modules/
coverage/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

Two lines do the security work. `.env` stays out, and `!.env.example` stays in.
The negation matters because the prefix rule would otherwise exclude the sample
that documents every variable, and that file is the one a new contributor
needs.

## 3. Remove what was already committed

Decide first whether history matters. Rebuild the repo clean when it has one
commit and no forks. Take the surgical path when anyone has cloned it.

```bash
# stop tracking, keep on disk
git rm -r --cached .venv
git commit -m "hygiene: stop tracking the virtualenv"

# purge from every commit, when the file held a secret or bloat
git filter-repo --path .venv --invert-paths
```

`git filter-repo` rewrites every hash, so push with `--force-with-lease` and
tell anyone with a clone to re-clone rather than pull. `--force` alone can drop
a commit someone else pushed in between.

Removing a secret from history does not un-leak it. Rotate it first, then
rewrite.

## 4. CI that catches the drift

Three gates pay for themselves immediately. Put them in
`.github/workflows/ci.yml`. The plugin ships a working one in
`templates/repo/ci.yml`.

- **Tests.** The floor, not the point.
- **Tracked-yet-ignored.** `git ls-files -i -c --exclude-standard` must be
  empty. Catches the venv commit, the config file with real values, the editor
  cache.
- **Secret scan.** gitleaks or the plugin's validator. A credential committed
  once is a credential in every clone forever.

Add a fourth when the repo has an invariant worth defending: a layering rule, a
forbidden import, a generated file that must match its source.

**Every gate must pass on the current tree before it is committed.** A gate
that is red on day one gets disabled in week one. If a gate fails, fix the code
or narrow the gate to the invariant that is actually true, and say in a comment
why it was narrowed.

## 5. Keep the tree readable

- **One concern per directory.** `tools/` for scripts that are not part of the
  product, `docs/` for narrative, `tests/` mirroring the source layout.
- **No generated artefact in the tree** unless consumers need it without a
  build step. If you keep one, have CI regenerate and diff it.
- **No dated filenames** for anything that stays alive. `notes-2026-10-24.md`
  is a record, `design.md` is a document with a history.
- **A `docs/` index** once there are more than three documents, so a reader
  finds the one they need without listing the directory.

## Checklist

- [ ] `git ls-files -i -c --exclude-standard` prints nothing
- [ ] `.env` ignored and `.env.example` present and not ignored
- [ ] No build output or dependency tree tracked
- [ ] Any secret ever committed has been rotated
- [ ] CI runs tests plus the tracked-yet-ignored gate
- [ ] Every CI gate passes on the current tree
- [ ] `docs/` indexed once it holds more than three documents
