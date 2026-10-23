#!/usr/bin/env bash
# Claude Code PreToolUse hook (Bash): before any `git commit`, run lint and check that no model
# change is missing its migration. Exit 2 blocks the commit and shows the agent why.
set -uo pipefail

command="$(jq -r '.tool_input.command // ""')"
# Anything that is not a commit passes straight through (also matches `cd x && git commit`).
if ! grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' <<<"$command"; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 1
log="$(mktemp)"
trap 'rm -f "$log"' EXIT

fail() {
  {
    echo "Commit blocked: $1"
    tail -n 40 "$log"
  } >&2
  exit 2
}

make lint >"$log" 2>&1 || fail "make lint failed (fix it, or run make format)."
for service in app auth; do
  (cd "services/$service" && uv run --quiet python manage.py makemigrations --check --dry-run) >"$log" 2>&1 \
    || fail "services/$service has model changes without a migration (run makemigrations)."
done
exit 0
