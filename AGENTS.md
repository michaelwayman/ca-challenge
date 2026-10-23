# Brief for AI assistants working in this repo

Read the @CHALLENGE.md file


## Commands

- `make up`: build and start everything, then run both migrations. `make reset` wipes the databases.
- `make test`: the library, both services and the frontend. The service tests need
- `make lint` before every commit: ruff, djlint, eslint, stylelint, tsc, prettier.
- Run `uv run python manage.py makemigrations --check` in a service after changing its models.

## Rules

- **Shared library.** Only code related to both services may go in it.
- **Dependencies** Never introduce new dependencies or packages without asking.
- **API.** Don't change parameter names or the row shape without updating the README's contract table.
- **Frontend.** Prefer native elements to hand-built ARIA widgets.
- **Scope.** Build what is asked. If something beyond the brief looks worth adding, propose it and wait.
- **README.** Be clear and concise. Less is more.
- **Commits** say why, not only what, and record any AI default kept or a proposal overridden.
