#!/usr/bin/env bash
# Shows the auth flow against the running stack (run `make up` first).
#
#   1. Log in as an editor (admin) and as a reader (sarah_k).
#   2. Edit a brand's description with no token, as a reader, and as an editor.
#   3. Demote the editor in the auth service: the same token is refused at once.
#   4. Stop the auth service: reading still works, writing fails closed (503).
#
# Usage: scripts/demo-auth.sh [brand-slug]      (default: acme-insurance)
# The same story in Python, with no Docker needed: scripts/demo_auth.py
set -euo pipefail
cd "$(dirname "$0")/.."

APP=http://localhost:8000
AUTH=http://localhost:8001
BRAND=${1:-acme-insurance}
FAILURES=0
EDITOR_TOKEN=
ORIGINAL_DESCRIPTION=

# --- helpers -----------------------------------------------------------------

heading() {
  printf '\n\033[1m== %s\033[0m\n' "$1"
}

# Prints the HTTP status code of a curl call and nothing else.
http_status() {
  curl -s -o /dev/null -w '%{http_code}' "$@"
}

# Reads one field from a JSON document on stdin.
json_field() {
  python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

# Runs a manage.py command inside the auth container.
auth_manage() {
  docker compose exec -T auth python manage.py "$@"
}

# Gives or takes away the editor role in the auth service. $1 is add or remove.
change_editor_role() {
  auth_manage shell --no-imports -c "
from accounts.models import Role, User
roles = User.objects.get(username='admin').roles
getattr(roles, '$1')(Role.objects.get(name='editor'))
"
}

# log_in USERNAME PASSWORD  ->  prints an access token
log_in() {
  curl -s -X POST "$AUTH/api/auth/v1/token/" \
    -H 'Content-Type: application/json' \
    -d "{\"username\": \"$1\", \"password\": \"$2\"}" | json_field access_token
}

# edit_description TOKEN TEXT  ->  prints the HTTP status. Use "none" for no token.
edit_description() {
  local token=$1 text=$2 body
  body=$(python3 -c 'import json, sys; print(json.dumps({"description": sys.argv[1]}))' "$text")
  local headers=(-H 'Content-Type: application/json')
  if [ "$token" != none ]; then
    headers+=(-H "Authorization: Bearer $token")
  fi
  http_status -X PATCH "$APP/api/brands/$BRAND/" "${headers[@]}" -d "$body"
}

current_description() {
  curl -s "$APP/api/brands/$BRAND/" | json_field description
}

# check WHAT EXPECTED_STATUS ACTUAL_STATUS  ->  one line, marked ok or FAIL
check() {
  local mark=ok
  if [ "$3" != "$2" ]; then
    mark=FAIL
    FAILURES=$((FAILURES + 1))
  fi
  printf '  %-26s %s (expected %s)  %s\n' "$1" "$3" "$2" "$mark"
}

# Runs however the script ends (even if it is interrupted), so the demo never leaves the stack
# changed: the auth service running, the editor role back, the original description back.
clean_up() {
  docker compose start auth > /dev/null 2>&1
  until [ "$(http_status "$AUTH/healthz")" = 200 ]; do sleep 1; done
  change_editor_role add > /dev/null 2>&1
  if [ -n "$EDITOR_TOKEN" ] && [ -n "$ORIGINAL_DESCRIPTION" ]; then
    edit_description "$EDITOR_TOKEN" "$ORIGINAL_DESCRIPTION" > /dev/null
  fi
}
trap clean_up EXIT

# --- the story ---------------------------------------------------------------

heading "Set up: import the WordPress users (their WordPress passwords carry over)"
auth_manage import_wordpress_users

heading "1. Log in with WordPress passwords (admin/admin, sarah_k/changeme)"
EDITOR_TOKEN=$(log_in admin admin)
READER_TOKEN=$(log_in sarah_k changeme)
echo "  editor token: ${EDITOR_TOKEN:0:40}..."
wrong=$(http_status -X POST "$AUTH/api/auth/v1/token/" \
  -H 'Content-Type: application/json' -d '{"username": "admin", "password": "wrong"}')
check "wrong password" 401 "$wrong"

ORIGINAL_DESCRIPTION=$(current_description)

heading "2. Edit the description of $BRAND"
check "no token" 401 "$(edit_description none 'x')"
check "reader" 403 "$(edit_description "$READER_TOKEN" 'x')"
check "editor" 200 "$(edit_description "$EDITOR_TOKEN" 'Edited by an editor')"
echo "  now reads: $(current_description)"

heading "3. Demote the editor; the same token stops working"
change_editor_role remove
check "demoted editor, same token" 403 "$(edit_description "$EDITOR_TOKEN" 'x')"
change_editor_role add
check "editor again" 200 "$(edit_description "$EDITOR_TOKEN" 'Edited by an editor')"

heading "4. Stop the auth service: reads work, writes fail closed"
docker compose stop auth > /dev/null
check "read the brand list" 200 "$(http_status "$APP/api/brands/")"
check "editor edit" 503 "$(edit_description "$EDITOR_TOKEN" 'x')"

heading "Done (the original description, the editor role and the auth service are put back)"
echo
if [ "$FAILURES" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$FAILURES check(s) failed."
  exit 1
fi
