#!/usr/bin/env python3
"""Shows the auth flow against the running stack, using only the Python standard library.

    python3 scripts/demo_auth.py [brand-slug]        (default: acme-insurance)

Needs `make up` to be running, and development passwords for two users:

    docker compose exec auth python manage.py set_dev_password admin admin-pass
    docker compose exec auth python manage.py set_dev_password sarah_k reader-pass

(scripts/demo-auth.sh does that for you, and also shows a demotion and the auth service
going down, which need Docker.) The story here:

    1. Log in as an editor (admin) and as a reader (sarah_k).
    2. Edit a brand's description with no token, as a reader, and as an editor.
    3. Use the refresh token to get a new pair, and see that it only works once.
    4. Put the original description back.
"""

import json
import sys
import urllib.error
import urllib.request

APP = "http://localhost:8000"
AUTH = "http://localhost:8001"
BRAND = sys.argv[1] if len(sys.argv) > 1 else "acme-insurance"

failures = 0


def call(method, url, body=None, token=None):
    """Make one HTTP request. Returns (status code, parsed JSON body or None)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 (our own http URLs)
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:  # 4xx and 5xx are answers, not crashes
        raw = error.read()
        return error.code, json.loads(raw) if raw else None


def check(what, expected, actual):
    """Print one result line, and remember if it was not what we expected."""
    global failures
    mark = "ok" if actual == expected else "FAIL"
    if actual != expected:
        failures += 1
    print(f"  {what:<28} {actual} (expected {expected})  {mark}")


def heading(text):
    print(f"\n== {text}")


def log_in(username, password):
    """Returns the access and refresh tokens for a user."""
    status, tokens = call(
        "POST", f"{AUTH}/api/auth/v1/token/", {"username": username, "password": password}
    )
    if status != 200:
        sys.exit(f"Could not log in as {username} ({status}). Run set_dev_password (see the top).")
    return tokens["access_token"], tokens["refresh_token"]


def edit_description(token, text):
    """PATCH the brand's description. Returns the HTTP status."""
    status, _ = call("PATCH", f"{APP}/api/brands/{BRAND}/", {"description": text}, token)
    return status


def current_description():
    _, brand = call("GET", f"{APP}/api/brands/{BRAND}/")
    return brand["description"]


def main():
    heading("1. Log in")
    editor_token, editor_refresh = log_in("admin", "admin-pass")
    reader_token, _ = log_in("sarah_k", "reader-pass")
    print(f"  editor token: {editor_token}")
    print(f"  editor refresh token: {editor_refresh}")
    status, _ = call(
        "POST", f"{AUTH}/api/auth/v1/token/", {"username": "admin", "password": "wrong"}
    )
    check("wrong password", 401, status)

    original_description = current_description()
    try:
        heading(f"2. Edit the description of {BRAND}")
        check("no token", 401, edit_description(None, "x"))
        check("reader", 403, edit_description(reader_token, "x"))
        check("editor", 200, edit_description(editor_token, "<p>Edited by an editor</p>"))
        print(f"  now reads: {current_description()}")

        heading("3. Refresh the token")
        body = {"refresh_token": editor_refresh}
        status, new_tokens = call("POST", f"{AUTH}/api/auth/v1/refresh/", body)
        check("refresh", 200, status)
        check("new token works", 200, edit_description(new_tokens["access_token"], "<p>Again</p>"))
        status, _ = call("POST", f"{AUTH}/api/auth/v1/refresh/", body)
        check("same refresh token again", 401, status)
    finally:
        # Even if something above failed, leave the brand as we found it.
        heading("4. Clean up: put the original description back")
        check("restore", 200, edit_description(editor_token, original_description))


main()
print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
