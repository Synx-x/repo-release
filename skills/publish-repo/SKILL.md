---
name: publish-repo
description: >
  Take a repository from working to publicly readable. Use when the user says
  publish, open-source, make it public, ship a first release, or submit to a
  package index, plugin registry or marketplace. Covers the pre-publish audit,
  the artifact set, the order to build it in, and verifying the published page
  renders. Skip for private repos, internal forks, and scratch work nobody reads.
---

# Publishing a repository

A public repo is judged in about eight seconds, on the README's first screen
and the one-line description under its name. Everything here serves that.

One rule runs through all of it. Nothing about one machine may reach the repo.
An instruction naming an author's home directory resolves to nothing anywhere
else, and the reader never finds out it was meant for them.

## Order matters

Audit, then research, then build, then publish, then verify. Building first
means rewriting once the audit and the destination's conventions turn out to
differ.

## 0. Run the gate on a repo that is not this one

A validator only proves itself on repos it did not grow up beside. Every check
in this plugin was written against its own tree, and its own tree passed all of
them. Then a gate ran on a second repo and found two defects the plugin had
carried for three releases: a manifest pointing at a directory that did not
exist, and a transport check that matched `sse` inside the word "accessible".

So audit a second, unrelated repo before trusting a new check. The failures that
matter are the ones the author's own repo cannot show.

## 1. Audit before anything is public

Publishing is irreversible in the way that matters. The repo is indexed, cached
and forked. Run the validator over the tree first.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile public
```

It exits 1 on a blocking finding. Read every block before going further. The
three that most often fire on a working repo:

- **A tracked dependency tree.** `.venv/` or `node_modules/` committed before
  the ignore rule existed. Every file in the repo is judged again once it is
  out, and the vendored tree outnumbers anything you wrote.
- **A credential shape.** The scan catches the common key formats. It cannot
  catch a password typed into a config example, so read by eye every file that
  holds configuration, and rotate anything that ever touched the tree even
  after deletion, because git keeps the history.
- **A machine-local path in a file written for other machines.** Instruction
  files, contribution guides, and anything under `.agents/rules/`. Vendor the
  referenced file into the repo or drop the reference.

A finding you cannot fix is a finding worth stating to the user before the push,
not one worth suppressing.

## 2. Research the destination

Skip only for a bare GitHub repo with no ecosystem around it.

Read what got accepted, not the contribution docs. Docs go stale, merged
examples are what the maintainers actually took.

```bash
gh api repos/<owner>/<repo> --jq '{archived,pushed:.pushed_at}'
gh pr list --repo <owner>/<repo> --state merged --limit 10
```

Check three things:

- **Is the destination alive?** An archived repo, months of no merges, or a
  hundred stranded PRs means submission goes nowhere. Report that before
  building to fit it.
- **What does an accepted entry carry?** Mirror that file list exactly,
  including metadata files and naming case.
- **What limits are documented?** Name length, description length, image size.
  Validate against them rather than guessing.

## 3. Build the artifact set

Copy from the plugin's templates and fill them, rather than writing from
scratch. Every template carries the sections that matter and a comment on what
each one is for.

```bash
T="${CLAUDE_PLUGIN_ROOT}/templates"
cp "$T/repo/README.md" "$T/repo/CONTRIBUTING.md" "$T/repo/SECURITY.md" .
cp "$T/repo/CHANGELOG.md" "$T/repo/.env.example" .
cp "$T/repo/gitignore" .gitignore
cp "$T/license/MIT.txt" LICENSE
```

Mandatory, and the validator blocks without them:

- `README.md` saying what it is, how to install, how to use
- `LICENSE`
- a one-line repo description passed as `--description`

Add when they apply:

- a screenshot or demo, for anything with a visual surface
- a configuration table
- a section on how it works, recording the non-obvious findings
- topics, which drive discovery in search
- a release tag, when this ships a version (see `repo-versioning`)

### On the README

Lead with one sentence naming what it is. Put the image directly under it.
Install steps come before options. Keep the technical explanation last, because
most readers never reach it.

A status section earns trust when it is specific. Name the test count, the date
of the last live measurement, and what does not work. A vague "actively
maintained" reads as abandoned with extra words.

### On the screenshot

Take it on a clean, default environment rather than a customised one. Readers
need to see what they will get. Frame the subject whole, with margin, then crop
to whatever the destination requires.

## 4. Publish

```bash
gh repo create <owner>/<name> --public \
  --description "<one line, what it is>" \
  --source . --remote origin --push
gh repo edit --add-topic <topic1>,<topic2>,<topic3>
```

Describe what it is, not what it hopes to be. "Anthropic Messages API facade in
front of web chat providers" gets clicks. "A revolutionary AI orchestration
layer" gets closed.

## 4b. Set the About, which no validator can see

The About line and the topic list live on GitHub, not in the tree, so no local
check reaches them. That makes them the fields people forget: `harness-kit` was
published with no description and no topics at all, and nothing noticed.

```bash
gh repo edit --description "<one line, what it is>" \
  --add-topic t1 --add-topic t2 --add-topic t3
gh repo view <owner>/<repo> --json description,repositoryTopics
```

Set the description from the README's first screen, not from memory. Then read
it back and confirm it is non-empty, because `gh repo edit` reports success
either way.

The description is what a search result shows. The README is what a click
shows. A repo with one and not the other is half published.

## 5. Verify the published result

Done means the page renders, not that the push succeeded.

```bash
gh repo view <owner>/<repo> --json url,visibility,description,repositoryTopics,licenseInfo
gh api repos/<owner>/<repo>/contents --jq '.[].name'
curl -s -o /dev/null -w "%{http_code}\n" \
  https://raw.githubusercontent.com/<owner>/<repo>/main/<image>
```

A README image that 404s is the most common failure and the most visible one.
The fix is usually the branch name: a repo created on `master` with a README
pointing at `main`, or the reverse.

```bash
git rev-parse --abbrev-ref HEAD
```

## 6. Record what is still open

State plainly what remains. A stale screenshot, a homepage pointing nowhere, a
registry that cannot accept submissions yet, a test count nobody re-ran. An
honest gap list beats a claim of completeness, and it is the difference between
a repo someone trusts and one they quietly close.

## Failure modes

- **The directory is not a git repo yet.** Create it first, as its own repo on
  the branch you mean to publish:

  ```bash
  git init -b main
  ```

  Without its own `.git`, everything that resolves a path from the file's
  repository resolves against the enclosing superproject instead. A
  PreToolUse guard then reports every cited file as missing even though it sits
  right there, and the validator prints the branch as `detached` because no
  branch exists yet. Both read as content defects and are neither.

## Checklist

- [ ] Validator exits 0 on `--profile public`
- [ ] Every configuration file read by eye for secrets, not just by scan
- [ ] Destination checked for signs of life
- [ ] README leads with one sentence and an image, install before options
- [ ] LICENSE present with real text
- [ ] Description is one line stating what it is, read back from the repo
- [ ] Topics set, read back from the repo
- [ ] Every count the README states matches the tree
- [ ] Published page fetched and checked
- [ ] Every README image returns 200
- [ ] Open gaps written down
