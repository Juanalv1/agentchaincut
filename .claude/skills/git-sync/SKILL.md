---
name: git-sync
description: Keep this repo in sync across multiple PCs. Trigger: before editing any file, after finishing changes, "sync", "pull", "push", merge conflicts.
---

# Git Sync

Several machines work on this repo. Never work on stale code and never leave changes unpushed.

## Workflow

1. **Before any change**: `git pull --rebase --autostash`.
2. **Make the change.**
3. **After the change**:
   ```bash
   git add -A
   git commit -F- <<'MSG'
   <type>(<scope>): <what changed, specific>

   <why it changed, what is left>

   Status: <pending|in-progress|done>
   MSG
   git pull --rebase --autostash
   git push
   ```

## Rules

- Every commit is descriptive: say WHAT changed and WHY. Never "update", "fix", "changes", "wip".
- Every commit ends with a `Status:` trailer, always:
  - `pending` — task defined or scaffolded, real work not started.
  - `in-progress` — partially done; the body says what is left.
  - `done` — task finished and checked.
- Example:
  ```
  feat(api): add /cuts endpoint to list chain cuts

  Exposes cut history for the dashboard. Pagination still missing.

  Status: in-progress
  ```
- If pull or rebase hits a conflict: STOP, show the conflicting files, and ask the user. Never `--force` push, never `reset --hard`.
- Do not commit secrets (`.env`, keys). Check `git status` before `git add -A`.

## Automation

`.claude/settings.json` enforces this with hooks:
- `SessionStart` and `PreToolUse` (Edit/Write) → `.claude/hooks/git-pull.sh` (throttled to 60s).
- `Stop` → `.claude/hooks/git-push.sh`: if there are uncommitted changes it blocks once and asks Claude to commit with the format above; then pull --rebase and push. Fallback commit (`Status: in-progress`) only if Claude did not commit.
