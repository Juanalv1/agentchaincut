#!/usr/bin/env bash
# On Stop: require Claude to commit with a descriptive message and a Status
# trailer, then pull --rebase and push.
input=$(cat)
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git remote get-url origin >/dev/null 2>&1 || exit 0

if [ -n "$(git status --porcelain)" ]; then
  # First Stop with a dirty tree: block and ask Claude to write the commit.
  if ! echo "$input" | grep -q '"stop_hook_active": *true'; then
    cat >&2 <<'MSG'
Uncommitted changes. Commit them now following the git-sync skill:
  <type>(<scope>): <what changed>

  <why / details>

  Status: pending | in-progress | done
Use "done" only if the task is finished; "in-progress" if partially done; "pending" if only scaffolding/notes.
MSG
    exit 2
  fi
  # Second attempt still dirty: fallback commit so nothing is lost.
  git add -A
  git commit -m "chore: sync uncommitted changes from $(hostname)" \
             -m "Status: in-progress" >/dev/null 2>&1
fi

[ -z "$(git log @{u}..HEAD 2>/dev/null)" ] && git rev-parse @{u} >/dev/null 2>&1 && exit 0

if ! out=$(git pull --rebase --autostash 2>&1); then
  echo "git pull before push failed (conflict?) — resolve manually:" >&2
  echo "$out" >&2
  exit 2
fi
if ! out=$(git push -u origin HEAD 2>&1); then
  echo "git push failed:" >&2
  echo "$out" >&2
  exit 2
fi
exit 0
