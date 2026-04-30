---
name: gitflow-feature
description: 'Manage the full git-flow feature branch lifecycle. Use when the user asks to "start a new feature", "begin a feature", or "create a feature branch". Covers: (1) Checking out and pulling develop, (2) Creating a git-flow feature branch, (3) After task completion - finishing the feature, creating a release branch derived from the last tag, finishing the release, pushing develop and main, and cleaning up local branches.'
license: MIT
allowed-tools: Bash
---

# Git Flow Feature Workflow

## Overview

Manages the complete lifecycle of a git-flow feature branch — from creation through release — following the Vincent Driessen branching model, adapted to use `main` as the production branch.

## Trigger Phrases

Activate this skill when the user says:
- "start a new feature [name]"
- "begin a feature [name]"
- "create a feature branch [name]"

## Phase 1: Start the Feature

When the user asks to start a feature, execute these steps in order:

### 1. Switch to develop and pull latest

```bash
git checkout develop
git pull origin develop
```

### 2. Create the feature branch

```bash
git flow feature start <feature-name>
```

The feature branch will be named `feature/<feature-name>` automatically by git-flow.

Confirm to the user which branch is now active before proceeding with any work.

---

## Phase 2: Finish the Feature (ONLY when user explicitly requests)

**CRITICAL: NEVER run Phase 2 autonomously or on autopilot.** When your implementation work is complete, you MUST:
1. State that the task is complete and all checks pass
2. Tell the user you are waiting for their explicit instruction to merge/finish the feature
3. **STOP and WAIT** — do NOT proceed to Phase 2

Only run Phase 2 when the user **explicitly** says something like "merge it", "finish the feature", "we're done", or "go ahead and merge". Completing a task does NOT mean you should merge. The user decides when to merge.

### 1. Remove dead code

Before running any quality gates, identify and remove all dead code introduced or exposed by the feature work:
- Unused imports, unreferenced helpers, orphaned functions
- Old files that were replaced by new ones
- Any files or exports that are no longer imported anywhere

Commit the cleanup if there are changes:
```bash
git add -A
git commit -m "chore: remove dead code before quality gates

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### 2. Run ALL quality gates and verify they pass

**ALL** of the following must pass **in this order** before proceeding. Do NOT finish the feature if ANY fails.

#### a) Python syntax check
```bash
python -m py_compile cloak_extract.py
```
Must exit 0. Any `SyntaxError` blocks the merge.

#### b) Import / version smoke test
```bash
python cloak_extract.py --version
```
Must print the version and exit 0. This proves the module loads end-to-end with no import-time errors.

#### c) Help screen smoke test
```bash
python cloak_extract.py --help
```
Must print the help text and exit 0. This proves argparse wiring is intact.

If any gate fails, fix the issue and **re-run from that gate onwards**.

### 3. Finish the feature branch

```bash
git flow feature finish <feature-name>
```

This merges `feature/<feature-name>` into `develop` and deletes the feature branch locally.

### 4. Derive the next release version

Get the last release tag to determine the next version:

```bash
git tag --sort=-version:refname | head -5
```

Increment the **patch** version by default (e.g. `v0.0.1` → `v0.0.2`).
Ask the user if a **minor** or **major** bump is more appropriate for the changes made.

If there are no tags yet, start at `v0.1.0` (or `v1.0.0` for a stable first release).

### 5. Update the CHANGELOG

Before creating the release, update `CHANGELOG.md` with the new version section and commit it to develop:

```bash
git add CHANGELOG.md
git commit -m "chore(release): prepare release <version>

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

If `CHANGELOG.md` does not yet exist, create it with a `Keep a Changelog` style header and the new version section.

### 6. Start the release branch

```bash
git flow release start <version>
```

### 7. Finish the release branch

```bash
git flow release finish <version> -m "Release <version>"
```

This will:
- Merge `release/<version>` into `main`
- Tag `main` with `<version>`
- Merge `release/<version>` back into `develop`
- Delete the local `release/<version>` branch

### 8. Push develop, main, and tags

```bash
git push origin develop
git push origin main
git push origin --tags
```

### 9. Clean up (if branches still exist locally)

```bash
git branch -d feature/<feature-name> 2>/dev/null || true
git branch -d release/<version> 2>/dev/null || true
```

---

## Version Bump Guidelines

| Change Type        | Bump   | Example              |
| ------------------ | ------ | -------------------- |
| Bug fix / patch    | Patch  | v0.0.1 → v0.0.2      |
| New functionality  | Minor  | v0.0.1 → v0.1.0      |
| Breaking change    | Major  | v0.0.1 → v1.0.0      |

When you bump the version, also update `__version__` in `cloak_extract.py` to match the new tag (without the leading `v`).

---

## Safety Rules

- **NEVER** run `git flow feature finish` until all quality gates pass and the **user explicitly requests** the merge (e.g. "merge it", "finish the feature", "we're done")
- **NEVER** start Phase 2 autonomously — even if all tasks are complete and gates pass, you MUST wait for the user to explicitly say to merge
- When your implementation work is done, state that the task is complete and you are waiting for the user's instruction to merge
- **NEVER** use `--no-verify` or bypass pre-commit hooks
- **NEVER** force push to `develop` or `main`
- **ALWAYS** confirm the feature name and version with the user before finishing
- If `git flow release finish` opens an editor for the tag message, pass `-m` to avoid interactive prompts
