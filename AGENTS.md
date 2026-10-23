# Agent brief

`CHALLENGE.md` is the source of truth for deliverables and scope. Read it before planning new work.

## Commands

- `make up` builds, starts and imports; `make reset` wipes the databases.
- `make test` runs every suite (the service tests need `make up`).
- Lint and the migration check run automatically before `git commit` (`.claude/settings.json`).

## Rules

- `libs/shared` holds only code both services use.
- Native HTML elements over hand-built ARIA widgets.
- Build what is asked; propose anything extra and wait.
- Keep the README short.
- Commit messages say why, and note any AI default kept or proposal overridden.
