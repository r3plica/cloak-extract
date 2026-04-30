# AGENTS.md — Working in this repository

These rules apply to any AI coding agent (Copilot CLI, Claude Code, Cursor, etc.)
working in this repository. **Read this file before making any changes.**

## Branching policy: gitflow is mandatory

This repository uses **git-flow** (Vincent Driessen branching model), adapted
to use `main` as the production branch.

- `main`     — production, always tagged, never committed to directly
- `develop`  — integration branch for completed features
- `feature/*` — short-lived branches off `develop`
- `hotfix/*`  — short-lived branches off `main`
- `release/*` — short-lived branches off `develop`, merged to both

### ⚠️ Hard rule: NO direct changes

**Before making ANY code change**, you MUST first initialise the appropriate
git-flow branch via one of the two skills in `.github/skills/`:

| User intent                          | Skill to invoke         | Starting branch |
| ------------------------------------ | ----------------------- | --------------- |
| New functionality / non-urgent work  | `gitflow-feature` (Phase 1) | `develop`       |
| Urgent fix to production behaviour   | `gitflow-hotfix` (Phase 1)  | `main`          |

If the user asks you to change something without specifying which flow, **ask
them first** whether it should be a feature or a hotfix. Do not edit any file
on `main` or `develop` directly.

### Workflow at a glance

1. **Start.** Invoke `gitflow-feature` or `gitflow-hotfix` Phase 1 to create
   the branch.
2. **Work.** Make changes, commit on the feature/hotfix branch.
3. **Stop.** When the work is complete, state that and **wait** for the user
   to explicitly say "merge it" / "finish it" / "we're done".
4. **Finish.** Only then invoke Phase 2 of the relevant skill, which runs the
   quality gates and performs the merge.

The full procedures are documented in:

- `.github/skills/gitflow-feature/SKILL.md`
- `.github/skills/gitflow-hotfix/SKILL.md`

## Commit messages

Always include the following trailer on commits you author:

```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## What never to do

- ❌ Edit files while checked out on `main` or `develop`
- ❌ Run `git flow * finish` autonomously — wait for explicit user approval
- ❌ Force-push to `main` or `develop`
- ❌ Use `--no-verify` to bypass hooks
- ❌ Bump versions without updating `__version__` in `cloak_extract.py` and `CHANGELOG.md`
