# Contributing

<!--
Lead with whatever is most confusing about this repo. That is the paragraph a
new contributor needs most, and it is usually the one the author never writes
because it stopped being confusing months ago.

If there are two ways to run it, say which one ships.
-->

## Setup

```bash
<clone, install dependencies, the first command that proves it works>
```

## Verify

```bash
<the test command>
```

<How many tests are expected to pass. Say it, so a lower number is obviously
wrong rather than ambiguous.>

## Run

```bash
<the command that starts it for development>
```

## Branching

- Branch from `<default branch>`.
- One concern per branch.
- <commit message convention, and why it is that shape>

## Before opening a pull request

- [ ] Tests pass locally
- [ ] A changelog entry is added under `## [Unreleased]`, if the change is
      user-visible
- [ ] No secrets, local paths, or build output in the diff
- [ ] The description says what breaks, if anything does

## Reporting a bug

Include the version, the command you ran, and what you expected instead. A
reproduction that fails in one paste is worth ten paragraphs of description.
