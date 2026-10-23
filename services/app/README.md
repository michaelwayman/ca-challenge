# app: the main site

The Django app that replaces the WordPress site. It serves the home, brand and review pages at the same
URLs as WordPress, the brand-listing API, and a React `<BrandList />` on `/brand/`. It owns the domain data
(brands, industries, reviewers, reviews). It stores no passwords and no roles: tokens are verified locally
against the [auth service](../auth/README.md)'s public keys, and the one write endpoint asks the auth service for
the caller's current roles.

| | |
|---|---|
| Pages | `/`, `/brand/`, `/brand/<slug>/`, `/review/<slug>/` |
| API | `GET /api/brands/` (`industry`, `ordering`, `page`, `page_size`), `GET` and `PATCH /api/brands/<slug>/` (editor only) |
| Code | `catalog/` (models, views, API, importer), `frontend/` (React and SCSS), `templates/` |

## Quickstart

From the repository root, with Docker only:

```bash
cp .env.example .env
make up                    # builds, starts the app (:8000) and auth (:8001), imports the WordPress data
```

On the host, with [uv](https://docs.astral.sh/uv/) (databases still in Docker):

```bash
docker compose up -d db-app db-auth
make assets                # compile the CSS and the React bundle (the image does this itself)
cd services/app
uv run python manage.py migrate
uv run python manage.py runserver 8000
uv run pytest              # tests
```

## Useful commands

```bash
python manage.py import_wordpress [--dry-run] [--prune]   # the migration; safe to re-run
make js                    # rebuild the React bundle after changing frontend/src
make dev-watch             # rebuild the CSS and the bundle on every save (or make css-watch / make js-watch)
cd frontend && pnpm dev    # the component on :5173 with hot reload
```

## Configuration

Environment variables, all with development defaults: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `AUTH_JWKS_URL`, `AUTH_INTROSPECT_URL`, `AUTH_SERVICE_SECRET`,
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`. The migration also reads `WP_DB_*`.
