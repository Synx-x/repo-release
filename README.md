# repo-release

A Claude Code plugin that takes a repository from working to publicly readable,
and keeps it readable afterwards. It ships four skills, a template set, and a
validator that a hook runs on the publish and release commands.

```
/repo-release:publish    publish surface, destination research, verification
/repo-release:hygiene    ignore rules, history cleanup, CI gates
/repo-release:version    version, changelog and tag agreeing
/repo-release:agent      AGENTS.md, bridges, project rules
```

## Install

```bash
claude plugin marketplace add Synx-x/repo-release
claude plugin install repo-release@repo-release
```

## Why a validator

A checklist in a skill is advice. Advice is skipped at the moment it matters
most, which is late in a session when the push is one command away.

The validator turns the checklist into an exit code:

```bash
python3 scripts/validate.py /path/to/repo --profile public
```

It exits 1 on a blocking finding, and the hook refuses the publish command. Two
profiles:

| Profile | Checks |
|---|---|
| `public` | README, LICENSE, ignored-but-tracked files, machine-local paths, credential shapes, cited paths, `.env.example`, bridges, ignore rules |
| `release` | all of `public`, plus manifest version, changelog entry and tag agreeing |

## What it catches

Each of these has shipped in a real repo before the check existed.

- **A tracked dependency tree.** `.venv/` committed before the ignore rule.
  Once public, the vendored tree outnumbers anything written by hand.
- **A credential shape.** AWS, GitHub, Anthropic, OpenAI, Slack, Google keys,
  and private key blocks. Narrow on purpose, because a broad pattern turns
  every documented placeholder into a blocker and the gate gets switched off.
- **A machine-local path.** A contributor's home directory named inside a
  contribution guide resolves to nothing on a reader's machine, and they never
  find out.
- **A bridge that diverged.** A tool file that restates conventions instead of
  importing the canonical guide drifts within a week.
- **A version with no changelog.** A tag nobody can read is a number, not a
  release.

## Templates

`scripts/scaffold.py` copies the full set into a repo and never overwrites an
existing file, because the usual case is adding the missing pieces to a repo
with a README worth keeping.

```bash
python3 scripts/scaffold.py . --name mytool --owner Synx-x --license MIT
```

It writes `README.md`, `AGENTS.md`, thin `CLAUDE.md` and `GEMINI.md` bridges,
`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`,
`.gitignore`, `.github/workflows/ci.yml`, and an example rule and workflow under
`.agents/`.

## Status

Working and tested: the validator, the scaffolder, and the hook. 63 tests pass.
Each check is tested against a fixture repo holding exactly the defect under
test, so a passing suite means the checks discriminate rather than that the
fixtures are empty.

Not yet measured: the hook against a real `gh repo create --public`. It has been
exercised by direct invocation only.

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `REPO_RELEASE_MODE` | `strict` | `off`, `warn` or `strict`. `strict` blocks the publish while a blocking finding stands. |

Strict is the default because the validator exits 0 on a clean tree. A guard
that only warns on a discriminating check is a guard nobody reads.

The hook fails open. Any error inside it allows the call, because a broken gate
must never strand the action it guards.

Two one-shot escapes exist and both are logged: `[publish-ok]` in a command,
`[release-ok]` in a version edit.

## How it works

`hooks/guard_publish.py` reads the Bash command or the edited file, decides
whether it publishes or changes a version, then runs `scripts/validate.py` and
exits 2 with the findings on stderr.

The guard triggers on `gh repo create --public`, `gh repo edit --visibility
public`, `gh release create`, `git push --tags`, `npm publish`, `twine upload`
and `cargo publish`, plus any edit to the version line in `pyproject.toml`,
`package.json` or `Cargo.toml`.

The skills explain why each check exists. The validator only says whether it
holds. Keeping the judgment out of the code is what makes the answer the same
on every run.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
