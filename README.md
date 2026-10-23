# brand-reviews

A Django replacement for the WordPress consumer-reviews site: server-rendered pages at the same URLs, a
brand-listing API, a React `<BrandList />`, an SCSS source tree, a separate auth service and a small shared
library. Every decision, with its alternatives, is logged in [DECISIONS.md](DECISIONS.md). Where I kept or
overrode the AI's proposals, and what changed after a practice panel review, is summarised in
[AI_WORKFLOW.md](AI_WORKFLOW.md). [AGENTS.md](AGENTS.md) is a draft brief for an AI tool working in this repo.

| Path | What |
|---|---|
| `services/app` | Main Django app, its own Postgres (:8000) |
| `services/auth` | Auth service, its own Postgres (:8001) |
| `services/app/frontend` | React `<BrandList />` and the SCSS source |
| `libs/shared` | Python package both services share: `shared.auth` (token contract, verification, DRF adapter) and `shared.wp_migration` (reading the WordPress database) |

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

**SCSS.** The source is `services/app/frontend/scss/` (entry `main.scss`). Compile it with
`cd services/app/frontend && pnpm build:css` (that is `sass scss/main.scss ../static/css/site.css
--style=compressed`), or `make css` / `make css-watch` from the root; the output is
`services/app/static/css/site.css`, which Django serves. `pnpm check:parity` compiles it and checks every rule in
`reference/theme.css` has a counterpart and every class used in the templates and components is defined.

**Services on the host** (needs [uv](https://docs.astral.sh/uv/)): `docker compose up -d db-app db-auth`, run
`make assets`, then `uv run python manage.py migrate && uv run python manage.py runserver 8000` in
`services/app` (and `8001` in `services/auth`). `make lint` and `make test` run everything.

## The brand API

`GET /api/brands/` is public and paginated.

| Param | Values | Notes |
|---|---|---|
| `industry` | an industry slug, repeatable | OR across values. An unknown slug gives an empty page, not an error, so a stale bookmark degrades gracefully. |
| `ordering` | `name` (default), `average_rating`, `review_count`; prefix `-` for descending | Unreviewed brands sort last either way; `name` then id break ties, so pages never repeat or drop a row. Anything else is a 400 listing the allowed values. |
| `page`, `page_size` | integers; `page_size` defaults to 12, capped at 50 | A page past the end is a 404. |

The response is DRF's page-number shape, `{count, next, previous, results}`. Each row is:

```json
{"name": "Acme Insurance Co.", "slug": "acme-insurance", "url": "/brand/acme-insurance/",
 "industries": [{"name": "Insurance", "slug": "insurance"}],
 "average_rating": 3.9, "review_count": 12, "excerpt": "Acme Insurance is a long-running…",
 "top_review": {"slug": "…", "title": "…", "rating": 5, "snippet": "…", "reviewer": "Sarah K.", "url": "/review/…/"}}
```

- `average_rating` is derived from the reviews (one decimal; `null` with no reviews). `excerpt` and `snippet` are
  plain text: render them as text, never as HTML.
- **"Top review" is the brand's highest-rated review, then the most recent, then the highest id.** Known bias:
  it skews positive, and since all seeded reviews share one date, the id decides among equal ratings.
- `industries` is a list because the model is many-to-many, like the WordPress taxonomy.

`GET /api/brands/<slug>/` returns the same row plus `description` (sanitized HTML). It never looks at the
`Authorization` header, so it cannot fail because of a token or the auth service. `PATCH /api/brands/<slug>/`
edits `description` only, for the `editor` role: 401 without a valid token, 403 for a reader, 400 for any other
field or a body with no text left once unsafe markup is removed, 415 for anything but JSON, and 503 if the auth
service cannot be asked for the caller's current roles. `PUT` and `DELETE` are 405.

## Get a token and call the protected endpoint

```bash
# Users keep their WordPress passwords: admin/admin (an editor), and changeme for the reviewers (readers).
# Log in: a 10-minute access token and a single-use refresh token.
TOKEN=$(curl -s -X POST localhost:8001/api/auth/v1/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Edit a brand: 401 without a token, 403 for a reader, 200 for an editor.
curl -s -X PATCH localhost:8000/api/brands/acme-insurance/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"description": "<p>A new description</p>"}'
```

The WordPress password hashes are imported as they are, verified at login by
`services/auth/accounts/hashers.py`, and replaced by a Django (PBKDF2) hash on each user's first successful login.
WordPress 6.8+ and plain bcrypt hashes are supported; older phpass (`$P$`) hashes are not, and those users are
imported without a usable password (the import reports them). `set_dev_password` still sets any password in
development.

`make demo-auth` walks through the whole flow, including a demotion and the auth service being down; `make demo-auth-py` runs the same story in Python (`scripts/demo_auth.py`), over HTTP only.

## The shared library

```bash
uv run --package shared --group test pytest libs/shared   # no service needed
```

To release: bump `version` in `libs/shared/pyproject.toml`, tag `shared/vX.Y.Z`, and build with
`uv build --package shared`. Each service depends on a range (`shared[...]>=0.2,<0.3`), so it takes the new
version by widening that range and running `uv lock`, and can lag the other. Only the workspace install is wired
here (there is no publishing pipeline), so in practice both services run the library's current source.

## Housekeeping

Every login and every refresh adds a refresh-token row, and redeeming one only marks it revoked, so the auth
database grows until it is purged. `purge_tokens` deletes refresh tokens past their expiry and signing keys
retired longer ago than one access-token lifetime plus the JWKS cache time:

```bash
docker compose exec auth python manage.py purge_tokens --dry-run   # counts only
docker compose exec auth python manage.py purge_tokens
```

In production it would run on a schedule (cron or a Kubernetes CronJob); it is safe to run at any time.

## The migration

`make up` already runs it. By hand (the WordPress source is a throwaway MariaDB loaded from
`data/wordpress-dump.sql`, started with `make wp-source`):

```bash
docker compose exec app python manage.py import_wordpress             # add --dry-run or --prune
docker compose exec auth python manage.py import_wordpress_users
```

It is safe to re-run: rows are matched on their WordPress id (`wp_id`) and updated in place, the whole run is one
transaction, nothing is deleted unless you pass `--prune`, and a brand's description edited in Django is kept. A
second run reports `unchanged` for everything. Reading WordPress is `shared.wp_migration.source`, which both services
use; turning its rows into each service's models is in the commands themselves
(`services/app/catalog/management/commands/import_wordpress.py` and
`services/auth/accounts/management/commands/import_wordpress_users.py`).

## Modeling decisions

- **Average rating is derived from the reviews.** WordPress stores one per brand and it disagrees with the real
  reviews for 4 of 5 brands (HomeShield Pro: 3.9 stored, 3.08 from its 12 reviews), so it is not imported.
- **Reviewers are a profile, not a Django user.** The app stores no passwords or roles; the link to the auth
  service is a UUIDv5 of the WordPress user id, so both importers agree without calling each other.
- **Industries are many-to-many**, like the WordPress taxonomy, though every seeded brand has one.
- **One `description` per brand** (WordPress has no excerpt). It is sanitized on every save and rendered as HTML
  only on the brand page; cards show an escaped plain-text excerpt.
- **The main app verifies tokens locally**, so an auth outage never takes the site down; the one write endpoint
  also asks auth for the user's current roles and fails closed (503). The main app has no admin, no sessions and
  no user table of its own: it stores no passwords and no roles.

**Deliberately not ported:** the WordPress admin (out of scope; the auth service's own admin is where roles are
granted), the `/review/` and `/industry/<slug>/` archives, and static pages such as `/about/`. The main app's
admin, the `/review/` archive and static pages were built after the original scope and removed after a practice
panel review; see [AI_WORKFLOW.md](AI_WORKFLOW.md).

## With more time

Rate-limit `/token/` and detect refresh-token reuse; keep signing keys in a KMS; add CI and a production setup
(gunicorn, hashed static files, real secrets); publish the library as a versioned wheel; automate the
accessibility checks (the star colours are WordPress's and miss 3:1 contrast); batch the migration for 100x data.

## Where I kept the AI's defaults

Monorepo with one uv workspace and a Postgres per service, Django 5.2 with DRF, the ruff and front-end toolchain,
Ed25519 token signing with 10-minute and 7-day lifetimes, MariaDB as the migration source, and skeleton loading
states in the React list: boring, well known and easy to review. Where I chose against the proposal: industries
are many-to-many (not a foreign key), the list uses TanStack Query (not a hand-written hook), and breaking token
changes use a version claim (not expand/contract). The full list, and the changes made after a practice panel
review, are in [AI_WORKFLOW.md](AI_WORKFLOW.md).
