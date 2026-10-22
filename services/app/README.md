# app: the main site

The Django app that replaces the WordPress site. It serves the brand, review and static pages at the same
URLs as WordPress, the brand-listing API, a React `<BrandList />` on `/brand/`, and a Django admin. It owns the
domain data (brands, industries, reviewers, reviews, pages). It stores no passwords: tokens are verified locally
against the [auth service](../auth/README.md)'s public keys, and editors sign in to the admin with their
auth-service login.

| | |
|---|---|
| Pages | `/`, `/brand/`, `/brand/<slug>/`, `/review/`, `/review/<slug>/`, `/about/`, `/contact/` |
| API | `GET /api/brands/` (`industry`, `ordering`, `page`, `page_size`), `GET` and `PATCH /api/brands/<slug>/` (editor only) |
| Admin | `/admin/` |
| Code | `catalog/` (models, views, API, admin), `frontend/` (React and SCSS), `templates/` |

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
cd frontend && pnpm dev    # the component on :5173 with hot reload
```

## Configuration

Environment variables, all with development defaults: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `AUTH_JWKS_URL`, `AUTH_TOKEN_URL`, `AUTH_INTROSPECT_URL`, `AUTH_SERVICE_SECRET`,
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`. The migration also reads `WP_DB_*`.
