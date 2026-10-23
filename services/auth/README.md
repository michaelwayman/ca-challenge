# auth: users, roles and tokens

A small Django service that owns identity: users, roles (`reader`, `editor`), login, refresh tokens and the
signing keys. It issues short-lived signed tokens that other services verify locally with the public keys it
publishes, so they keep working if it is down. It has its own database and a Django admin for managing users.

| | |
|---|---|
| `POST /api/auth/v1/token/` | Log in: `{"username", "password"}` returns an access token (10 minutes) and a refresh token (7 days) |
| `POST /api/auth/v1/refresh/` | Exchange a refresh token for a new pair (each refresh token works once) |
| `POST /api/auth/v1/introspect/` | For other services only (needs the `X-Service-Secret` header): the user's current roles |
| `GET /.well-known/jwks.json` | The public keys tokens are verified with |
| `GET /healthz`, `/admin/` | Health check, and the admin (staff users only) |

Token handling is shared with the main app through [`libs/shared`](../../libs/shared) (`shared.auth`).

## Quickstart

From the repository root, with Docker only:

```bash
cp .env.example .env
make up                    # starts auth on :8001 (and the app on :8000), imports the users
curl -s -X POST localhost:8001/api/auth/v1/token/ \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}'   # the WordPress password
```

On the host, with [uv](https://docs.astral.sh/uv/) (database still in Docker):

```bash
docker compose up -d db-auth
cd services/auth
uv run python manage.py migrate
uv run python manage.py runserver 8001
uv run pytest              # tests
```

## Useful commands

```bash
python manage.py import_wordpress_users                  # WordPress users with their WordPress passwords; safe to re-run
python manage.py set_dev_password <username> <password>  # development only (refuses unless DEBUG is on)
python manage.py rotate_signing_key [--retire-old]       # add a key; --retire-old retires stale ones later
python manage.py purge_tokens [--dry-run]                # delete expired refresh tokens and long-retired keys
python manage.py createsuperuser                         # a staff user for /admin/
```

## Configuration

Environment variables, all with development defaults: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `AUTH_SERVICE_SECRET` (shared with the app), `AUTH_TOKEN_VERSION_APP`, `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`. The user import also reads `WP_DB_*`.
