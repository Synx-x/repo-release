---
name: agent-native-repo
description: >
  Make a repository workable by any AI tool and any new developer without tribal
  knowledge. Use when the user says "make this repo agent-native", "set up
  AGENTS.md", "onboard a second developer", "add project rules", or starts a
  project and wants the convention layer from the start. Produces AGENTS.md as
  the single canonical guide, thin bridges for each tool, and rules that cite
  real code. Skip for a throwaway script and for a repo published with no
  intention of accepting contributions.
---

# Agent-native repository

One canonical guide, read by every tool. Conventions that cite real code. A
validator that fails when the docs drift away from it.

Pattern adapted from `github.com/fullstackhero/dotnet-starter-kit`, worth
reading if you want the original.

## The shape

```
AGENTS.md                    canonical, tool-neutral, the map
CLAUDE.md                    5-line bridge that imports AGENTS.md
GEMINI.md                    5-line bridge that imports AGENTS.md
.agents/rules/*.md           conventions, read on demand, indexed from AGENTS.md
.agents/skills/*/SKILL.md    step-by-step recipes
.agents/workflows/*.md       review and orchestration playbooks
CONTRIBUTING.md              human onboarding
SECURITY.md                  reporting plus a deploy checklist
.env.example                 every variable, with a generate command
.github/workflows/ci.yml     tests plus hygiene gates
```

Templates for every one of these ship in `templates/repo/`.

## Rule zero: nothing may live outside the repo

Do this before anything else. Every reference to a path outside the repo is a
file the next developer will not have.

```bash
grep -rnE '/home/[a-z]+/|/Users/[a-z]+/|/srv/[^/]+/home/' \
  AGENTS.md CLAUDE.md CONTRIBUTING.md .agents/rules/ 2>/dev/null
```

Vendor the file into the repo and rewrite the path, or delete the reference.
A pointer at a machine-local file silently resolves to nothing, and nobody
discovers it was meant for them.

Tilde paths are fine. `~/.config/app/config.toml` is portable, because it
resolves on whatever machine reads it.

## Step 1: Harvest what is already known

Do not invent conventions. Gather them, in this order of trust:

1. **The code.** Read it. It is the only source that cannot be stale.
2. **Existing project guides.** Usually dense with real invariants already.
3. **Session history.** Where this project's agent transcripts live. Mine them
   for bugs that took several attempts, decisions with their reasoning, and
   corrections the user gave more than once. This is the richest source of the
   gotchas that never reach a doc.
4. **Design docs, specs, retrospectives.**

Fan out across these in parallel when the repo is large. Tell each agent to
WRITE its report to a file and reply with a line count only. Long agent replies
get truncated and the report body is lost.

Tell them read-only, then check `git status` afterwards anyway. Agents write to
repos.

## Step 2: Verify before writing it down

Every claim from history is a claim about the past. Check it against the code
now.

A gotcha that has since been fixed belongs in the rules as *rationale for the
convention*, never as an open issue. Reporting a fixed bug as live wastes the
reader's time and costs you their trust in the whole document.

## Step 3: Write the canonical guide

The map, not the territory. Keep it lean and push detail into `.agents/rules/`.
Target 120 to 150 lines.

Sections, in order: title and one-line blurb, the canonical-guide note, what
this is, repo map table, tech stack, build and run, environment, branching,
**golden rules**, **rules index**, coding style, adding things, tooling
resources.

Two of those carry the weight.

**Golden rules.** Numbered, imperative, each with a one-line reason and a
pointer to its rule file. Aim for 8 to 12. Only invariants that cause real
damage when broken. If you cannot name the damage, it is not golden.

**Rules index.** A `Working on… | Read` table. This is what makes reading on
demand work instead of loading everything.

Each bridge is five lines and never diverges from the canonical guide:

```markdown
# Claude Code

The canonical project guide is **`AGENTS.md`** (tool-neutral). It is imported
below. Edit conventions there, not here.

@AGENTS.md
```

## Step 4: Project rules

One file per concern, 40 to 90 lines. No frontmatter, except a path-guard rule
which takes `paths:` globs.

Every non-obvious claim carries a `Source:` line with repo-relative paths.
Repo-relative, always. A path naming one author's home is the bug this whole
exercise exists to prevent.

The highest-value content is the failure that already happened. Write it
concretely:

> **This has bitten before.** A sync appended `"Account"` while the read model
> queried `"account"`. All 1287 transactions imported cleanly and the dashboard
> showed zero. There is no error for this. It fails silent.

That paragraph changes behaviour. "Use consistent casing" does not.

## Step 5: Skills and workflows

**Skills** are recipes, one directory each with a `SKILL.md`:

```yaml
---
name: add-endpoint
description: What it does and when to use it. Say when NOT to use it.
---
```

Numbered steps, real code from this repo, a checklist at the end. Put the steps
in dependency order and say why when the order matters.

**Workflows** are playbooks that delegate to skills. No `name` field. Procedure,
then a short checklist. Reference the rules, never restate them, or the copy
drifts.

Start with a code reviewer and an architecture guard. They pay for themselves
immediately.

## Step 6: Onboarding files

`.env.example` lists **every** variable, what it does, whether it is required,
and the command to generate it. Derive the list from the source, not memory:

```bash
grep -rhoE '(os\.environ\.get|os\.getenv)\(\s*"[A-Z][A-Z0-9_]+"' \
  --include='*.py' . | sort -u
grep -rhoE 'process\.env\.[A-Z][A-Z0-9_]+' --include='*.ts' . | sort -u
```

`CONTRIBUTING.md`: setup, run commands, how to verify, branching, commit style.
Lead with whatever is most confusing about the repo. Say which run path ships
when there are two.

`SECURITY.md`: private reporting, scope, and a deploy checklist naming every
variable that fails closed.

## Step 7: Verify

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" . --profile public
```

It checks that no absolute path reached a project guide, that bridges import
`AGENTS.md`, that cited paths resolve, and that `.env.example` covers what the
source reads.

## Checklist

- [ ] No guide references a path outside the repo
- [ ] AGENTS.md is canonical, bridges are 5 lines and import it
- [ ] Golden rules name the damage, each pointing at a rule file
- [ ] Rules index covers every rule file
- [ ] Rules cite repo-relative paths, and the cited files exist
- [ ] Claims from history verified against current code
- [ ] `.env.example` covers every variable the source reads
- [ ] CONTRIBUTING leads with the repo's most confusing thing
- [ ] Validator exits 0 on `--profile public`
