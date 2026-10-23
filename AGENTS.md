# Brief for AI assistants working in this repo

Draft context for an AI tool working in this code, for example in the live session; it is meant to be edited.
Read the challenge brief (`CHALLENGE.md` in the ConsumerAffairs challenge repo) and [DECISIONS.md](DECISIONS.md)
(why things are the way they are) before proposing changes.

## Layout

- `services/app`: the main Django app (`catalog`): models, the WordPress importer, server-rendered pages, and the
  `/api/brands/` API. `frontend/` holds the React `<BrandList />` and the SCSS source.
- `services/auth`: the auth service (`accounts`): users, roles, tokens, introspection, and the WordPress user
  import.
- `libs/shared`: the shared library. `shared.auth` holds the token contract, verification and the DRF adapter;
  `shared.wp_migration` holds the WordPress database reader and the migrated-user ids. Both services install it
  from the uv workspace.

## Commands

- `make up`: build and start everything, then run both migrations. `make reset` wipes the databases.
- `make test`: the library, both services and the frontend. The service tests need
  `docker compose up -d db-app db-auth`.
- `make lint` before every commit: ruff, djlint, eslint, stylelint, tsc, prettier.
- Run `uv run python manage.py makemigrations --check` in a service after changing its models.

## Rules

- **Service boundary.** The main app never stores passwords, roles or sessions, and never mints tokens. It
  verifies tokens with the shared library. Writes ask the auth service for current roles and fail closed with a
  503. Public reads never depend on the auth service.
- **Shared library.** Only code that both services import goes in it. Anything one service alone calls (the
  introspection client, for example) stays in that service. Keep it free of Django except the optional `drf`
  module.
- **HTML.** Stored HTML is sanitized in the model's `save()` (`catalog/sanitize.py`). Cards and API excerpts are
  plain text and must be rendered as text.
- **Migration.** Reading WordPress belongs in `shared.wp_migration`; writing models belongs in each service's
  import command. It must stay re-runnable: match on `wp_id`, use one transaction, change nothing on a second run,
  and delete nothing without `--prune`.
- **API.** Don't change parameter names or the row shape without updating the README's contract table.
- **Frontend.** Prefer native elements to hand-built ARIA widgets. The URL is the state for filters, sort and
  page. Styles go in `scss/components/_<name>.scss`, registered in `main.scss`, using token functions; run
  `pnpm check:parity`.
- **Scope.** Build what is asked. If something beyond the brief looks worth adding, propose it and wait.
- **Every change comes with tests.** A decision worth defending gets a line in `DECISIONS.md`, marked `decided` or
  `ai-default`.
- **Commits** say why, not only what, and record any AI default kept or proposal overridden.
