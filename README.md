# brand-reviews

A Django replacement for the WordPress consumer-reviews site: server-rendered pages at the same URLs, a
brand-listing API, a React `<BrandList />`, an SCSS source tree, a separate auth service and a small shared
library. Every decision, with its alternatives, is logged in [DECISIONS.md](DECISIONS.md).

| Path | What |
|---|---|
| `services/app` | Main Django app, its own Postgres (:8000) |
| `services/auth` | Auth service, its own Postgres (:8001) |
| `services/app/frontend` | React `<BrandList />` and the SCSS source |
| `libs/ca_authlib` | Python package both services share: token contract, verification, DRF adapter |

## Run it

You only need Docker. The image compiles the SCSS and the React bundle itself.

```bash
cp .env.example .env
make up      # builds, starts everything, then runs the migration (see below)
```

- Site and API: <http://localhost:8000> (the React list is at `/brand/`, the API at `/api/brands/`)
- Auth service: <http://localhost:8001> (`/.well-known/jwks.json`)
- `make down` stops it; `make reset` also deletes the databases, so the next `make up` seeds from scratch.

**React component.** `cd services/app/frontend && pnpm install && pnpm dev` serves it on
<http://localhost:5173>, proxying `/api` to the app. `make assets` rebuilds the bundle and CSS into
`services/app/static/`, which overrides the image's copy.

**Services on the host** (needs [uv](https://docs.astral.sh/uv/)): `docker compose up -d db-app db-auth`, run
`make assets`, then `uv run python manage.py migrate && uv run python manage.py runserver 8000` in
`services/app` (and `8001` in `services/auth`). `make lint` and `make test` run everything.

## Get a token and call the protected endpoint

```bash
# Users are imported with unusable passwords; set one for the WordPress admin (an editor).
docker compose exec auth python manage.py set_dev_password admin admin-pass

# Log in: a 10-minute access token and a single-use refresh token.
TOKEN=$(curl -s -X POST localhost:8001/api/auth/v1/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin-pass"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Edit a brand: 401 without a token, 403 for a reader, 200 for an editor.
curl -s -X PATCH localhost:8000/api/brands/acme-insurance/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"description": "<p>A new description</p>"}'
```

`make demo-auth` walks through the whole flow, including a demotion and the auth service being down; `make demo-auth-py` runs the same story in Python (`scripts/demo_auth.py`), over HTTP only.

## The shared library

```bash
uv run --package ca-authlib --group test pytest libs/ca_authlib   # no service needed
```

To release: bump `version` in `libs/ca_authlib/pyproject.toml`, tag `ca-authlib/vX.Y.Z`, and build with
`uv build --package ca-authlib`. Each service depends on a range (`ca-authlib>=0.1,<0.2`), so it takes the new
version by widening that range and running `uv lock`, and can lag the other. Only the workspace install is wired
here (there is no publishing pipeline), so in practice both services run the library's current source.

## The migration

`make up` already runs it. By hand (the WordPress source is a throwaway MariaDB loaded from
`data/wordpress-dump.sql`, started with `make wp-source`):

```bash
docker compose exec app python manage.py import_wordpress             # add --dry-run or --prune
docker compose exec auth python manage.py import_wordpress_users
```

It is safe to re-run: rows are matched on their WordPress id (`wp_id`) and updated in place, the whole run is one
transaction, nothing is deleted unless you pass `--prune`, and a brand's description edited in Django is kept. A
second run reports `unchanged` for everything. The code lives in each service's `management/commands/wp_migration/`.

## Modeling decisions

- **Average rating is derived from the reviews.** WordPress stores one per brand and it disagrees with the real
  reviews for 4 of 5 brands (HomeShield Pro: 3.9 stored, 3.08 from its 12 reviews), so it is not imported.
- **Reviewers are a profile, not a Django user.** The app stores no passwords or roles; the link to the auth
  service is a UUIDv5 of the WordPress user id, so both importers agree without calling each other.
- **Industries are many-to-many**, like the WordPress taxonomy, though every seeded brand has one.
- **One `description` per brand** (WordPress has no excerpt). It is sanitized on every save and rendered as HTML
  only on the brand page; cards show an escaped plain-text excerpt.
- **The main app verifies tokens locally**, so an auth outage never takes the site down; the one write endpoint
  also asks auth for the user's current roles and fails closed (503).

## With more time

Rate-limit `/token/` and detect refresh-token reuse; keep signing keys in a KMS; add CI and a production setup
(gunicorn, hashed static files, real secrets); publish the library as a versioned wheel; automate the
accessibility checks (the star colours are WordPress's and miss 3:1 contrast); batch the migration for 100x data.

## Where I kept the AI's defaults

Monorepo with one uv workspace and a Postgres per service, Django 5.2 with DRF, the ruff and front-end toolchain,
Ed25519 token signing with 10-minute and 7-day lifetimes, MariaDB as the migration source, and skeleton loading
states in the React list: boring, well known and easy to review. Where I chose against the proposal: industries
are many-to-many (not a foreign key), the list uses TanStack Query (not a hand-written hook), and breaking token
changes use a version claim (not expand/contract).
