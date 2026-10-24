# Project rules

## Multi-PC sync (MANDATORY)

This repo is edited from several PCs. To avoid overwriting each other's work:

- **Before any change**: run `git pull --rebase --autostash`.
- **After every change**: commit and `git push`. Commits are descriptive (what + why, Conventional Commits) and ALWAYS end with `Status: pending | in-progress | done`.
- Work directly on `main`. Never create branches unless the user explicitly asks for one.
- On conflict: stop and ask; never force-push or hard-reset.

Hooks in `.claude/settings.json` automate this, and the `git-sync` skill (`.claude/skills/git-sync/SKILL.md`) documents the workflow.
