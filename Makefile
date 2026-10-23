.PHONY: setup up down reset logs wp-source css css-watch js js-watch dev-watch assets release-shared demo-auth demo-auth-py lint format test test-py test-fe

setup:
	uv sync --all-packages
	cd services/app/frontend && pnpm install
	uv run pre-commit install

# Build and start everything, then import the WordPress data into both services. The imports are
# safe to repeat, so on a database that already has data this changes nothing.
up:
	docker compose --profile migration-source up -d --build --wait db-app db-auth app auth wp-db
	docker compose exec -T app python manage.py import_wordpress
	docker compose exec -T auth python manage.py import_wordpress_users

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
	rm -rf services/app/static

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
