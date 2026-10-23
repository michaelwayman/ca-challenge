# brand-reviews

A Django replacement for the WordPress brand-reviews site, with a separate auth service and a shared library.

| Path | What |
|---|---|
| `services/app` | Web app: the site, `/api/brands/` and the WordPress import. The React `<BrandList />` and the SCSS are in `services/app/frontend` |
| `services/auth` | Auth service: users, roles, login and tokens |
| `libs/shared` | Shared library: `shared.auth` (token verification, DRF permission) and `shared.wp_migration` (WordPress reader) |

## Run it locally

You need Docker.

```bash
cp .env.example .env
make up      # both services, their databases and the WordPress source; then runs the migration
```

- **Web app:** <http://localhost:8000>.
- **`<BrandList />`:** <http://localhost:8000/brand/>
- **Auth service:** <http://localhost:8001>.
- **`<BrandList />` on its own:** `cd services/app/frontend && pnpm install && pnpm dev` serves it at
  <http://localhost:5173>, proxying `/api` to the app.

## Compile the SCSS

The source is in `services/app/frontend/scss/` (entry `main.scss`); the output is
`services/app/static/css/site.css`, which Django serves. You need Node and pnpm (`make setup` installs the
packages).

```bash
make css                                                                          # minified, as the site serves it
cd services/app/frontend && pnpm exec sass scss/main.scss ../static/css/site.css  # readable, not minified
```

`make css-watch` rebuilds the readable version on every save.

## Get a token and call the protected endpoint

Users keep their WordPress passwords. `admin`/`admin` is an editor; the reviewers (`sarah_k`/`changeme`, …) are
readers.

```bash
TOKEN=$(curl -s -X POST localhost:8001/api/auth/v1/token/ -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X PATCH localhost:8000/api/brands/acme-insurance/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"description": "<p>New description</p>"}'
```

You get 401 without a token, 403 as a reader and 200 as an editor. `make demo-auth` runs the whole flow.

## The shared library

```bash
uv run --package shared --group test pytest libs/shared
```

How a new version reaches each service:
- **By default** both services use the working copy of `libs/shared`, which is a uv workspace member and is
  mounted into both containers. An edit reaches both at once.
- **Release:** `make release-shared BUMP=patch` (or `minor`, `major`) bumps the version, runs the tests, then
  tags `shared/vX.Y.Z` and pushes it.
- **Pin a service to a release:** `make up AUTH_SHARED=shared/v0.2.0`. Use `APP_SHARED` for the web app, or
  `SHARED` for both. The two services can run different versions. `make up` returns to the working copy.

## The migration

`make up` runs it. To run it by hand:

```bash
docker compose exec app python manage.py import_wordpress
docker compose exec auth python manage.py import_wordpress_users
```

It is safe to re-run: rows are matched on their WordPress id and updated in place, each run is one transaction,
and nothing is deleted unless you pass `--prune`. A second run reports everything `unchanged`.

## Decisions

### Modeling

- **The average rating is derived, not stored.** WordPress's stored `average_rating` disagrees with the brand's
  own reviews for 4 of 5 brands (HomeShield Pro: 3.9 vs 3.08), so it isn't imported.
- **Reviewers are a small profile, not Django users.** The auth service owns passwords and roles; the web app
  keeps a name and an id both importers derive from the WordPress user id.
- **Industries are many-to-many**, matching the WordPress taxonomy rather than today's one-per-brand data.
- **WordPress meta** became plain columns; the two Yoast fields went into a JSON column for the brand page's
  `<title>` and meta description.
- **"Top review"** is the highest-rated review, newest first on a tie. It skews positive.
- **Tokens are verified locally**, so reads never depend on the auth service. The write endpoint also asks auth
  for current roles, so a demotion applies at once; if auth is down, the edit fails with a 503.
- **WordPress passwords keep working**, and are re-hashed with Django's hasher on first login.

### With more time

- Harden the auth service, e.g. keep signing keys in a KMS and rate-limit login.
- Add CI, a real production setup, and a collaboration workflow (issues, standards, reviews).
- Improve how the agent is steered for further feature development.
- Add an `api/industries` endpoint for `<BrandList />`.
- Document the removal of the WordPress code once the migration is no longer needed.

### AI defaults I kept over my own preference

- **Using DRF in the auth service.** DRF is the one every Django reviewer knows, and a second paradigm would be one more thing to defend.
- **Using sync views and wsgi instead of async.** AI laid out scenarios that it's better to scale with workers instead.
- **Signing keys stored in the auth database.** It's the 1/2 measure between doing too much and not enough.
- **No type checker yet.** I'd add ty or mypy or pyright, but ruff and the test suite were enough for this size.
- **One uv workspace:** It's easier to develop using a mono-repo than separate repos.
- **Expand/contract for token changes:** add the new claim (auth writes old and new), move readers to it, then
  drop the old one. Readers ignore claims they don't know, so neither service has to deploy first. I first built
  a version claim instead, then went back to the AI's proposal as simpler and more standard.

### Where I overrode the AI

- **Documentation:** too detailed and verbose; the important parts were hard to find, so I cut it back.
- **Industries:** it proposed a foreign key; I made it many-to-many.
- **Brand descriptions:** it invented a second `short_description` field that WordPress never had. I kept one
  description, as WordPress does.
- **Data fetching:** it proposed a hand-written hooks; I used TanStack Query for caching and cancellation.
