# Which shared library each service runs. Both use the working copy (libs/shared) unless given a
# git tag: `make up AUTH_SHARED=shared/v0.2.0`, `make up APP_SHARED=... AUTH_SHARED=...`, or
# `make up SHARED=...` for both. A tag is exported to .build/<tag>/ (scripts/export-shared.sh).
SHARED ?=
APP_SHARED ?= $(SHARED)
AUTH_SHARED ?= $(SHARED)
shared_src = $(if $(1),.build/$(1)/libs/shared,libs/shared)
# Only the working copy is mounted over the image's copy (for live edits); a pinned tag is baked
# into the image, and its mount is parked where nothing imports it.
shared_mount = $(if $(1),/opt/pinned-shared-not-imported,/workspace/libs/shared)
export APP_SHARED_SRC := $(call shared_src,$(APP_SHARED))
export AUTH_SHARED_SRC := $(call shared_src,$(AUTH_SHARED))
export APP_SHARED_MOUNT := $(call shared_mount,$(APP_SHARED))
export AUTH_SHARED_MOUNT := $(call shared_mount,$(AUTH_SHARED))

.PHONY: setup up down reset logs wp-source css css-watch js js-watch dev-watch assets shared-export shared-version release-shared demo-auth demo-auth-py lint format test test-py test-fe

setup:
	uv sync --all-packages
	cd services/app/frontend && pnpm install
	uv run pre-commit install

# Build and start everything, then import the WordPress data into both services. The imports are
# safe to repeat, so on a database that already has data this changes nothing.
up: shared-export
	docker compose --profile migration-source up -d --build --wait db-app db-auth app auth wp-db
	docker compose exec -T app python manage.py import_wordpress
	docker compose exec -T auth python manage.py import_wordpress_users
	@$(MAKE) --no-print-directory shared-version

# Export each requested tag's libs/shared into .build/<tag>/ (nothing to do on the working copy).
shared-export:
	@for tag in $(sort $(APP_SHARED) $(AUTH_SHARED)); do ./scripts/export-shared.sh "$$tag" || exit 1; done

# The shared library version each running service imports.
shared-version:
	@for service in app auth; do \
		printf '%-5s shared %s from %s\n' "$$service:" \
			"$$(docker compose exec -T $$service python -c 'import shared; print(shared.__version__)')" \
			"$$(docker compose exec -T $$service printenv SHARED_SOURCE)"; \
	done

# Bump, check, commit, tag and push a release of libs/shared (scripts/release_shared.py).
# BUMP is patch, minor, major or X.Y.Z; ARGS passes options, e.g. ARGS=--dry-run or ARGS=--tag-current.
release-shared:
	uv run --quiet python scripts/release_shared.py $(BUMP) $(ARGS)

down:
	docker compose down

# Delete everything this project created: containers, networks, the database volumes and the
# host-built front-end assets. The next `make up` starts from nothing and seeds it again.
reset:
	docker compose --profile migration-source down --volumes --remove-orphans
	rm -rf services/app/static .build

logs:
	docker compose logs -f app auth

css:
	cd services/app/frontend && pnpm build:css

css-watch:
	cd services/app/frontend && pnpm dev:css

js:
	cd services/app/frontend && pnpm build:js

# Rebuilds the bundle on every save (no type check; `make js` and `make lint` run tsc).
js-watch:
	cd services/app/frontend && pnpm dev:js

# Rebuild the CSS and the React bundle on every change; a hard refresh shows them.
dev-watch:
	$(MAKE) -j2 css-watch js-watch

assets: css js

demo-auth:
	./scripts/demo-auth.sh

# The same flow in Python, over HTTP only (no Docker commands).
demo-auth-py:
	python3 scripts/demo_auth.py

wp-source:
	docker compose --profile migration-source up -d wp-db

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run djlint --configuration pyproject.toml services/app/catalog/templates services/app/templates --check
	cd services/app/frontend && pnpm lint && pnpm typecheck && pnpm format:check

format:
	uv run ruff check --fix .
	uv run ruff format .
	uv run djlint --configuration pyproject.toml services/app/catalog/templates services/app/templates --reformat
	cd services/app/frontend && pnpm format

test: test-py test-fe

test-py:
	uv run --package shared --group test pytest libs/shared
	uv run pytest scripts/tests
	uv run --package reviews-app pytest services/app
	uv run --package reviews-auth pytest services/auth

test-fe:
	cd services/app/frontend && pnpm test
