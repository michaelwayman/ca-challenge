# Build context is the repo root (the uv workspace and shared lib live there).

# Stage 1: compile the SCSS and the <BrandList /> bundle, so the image needs no Node on
# the host. The frontend scripts write to ../static, which is /build/services/app/static here,
# the same layout as the repository.
FROM node:22-slim AS assets
RUN npm install --global pnpm@12.6.0
WORKDIR /build/services/app/frontend
COPY services/app/frontend/package.json services/app/frontend/pnpm-lock.yaml services/app/frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY services/app/frontend/tsconfig.json services/app/frontend/vite.config.ts services/app/frontend/index.html ./
COPY services/app/frontend/scss scss
COPY services/app/frontend/src src
RUN pnpm build:css && pnpm build:js

# Stage 2: the app.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /workspace

# Dependencies first so this layer caches until a manifest changes.
COPY pyproject.toml uv.lock .python-version ./
COPY libs/shared/pyproject.toml libs/shared/
COPY services/app/pyproject.toml services/app/
COPY services/auth/pyproject.toml services/auth/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package reviews-app

# Then source. Workspace members install editable, so a bind-mounted ./libs
# gives live edits to the shared lib in dev.
COPY libs/shared libs/shared
# The front-end sources are only needed by the stage above, so they stay out of this image.
COPY --exclude=frontend services/app services/app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reviews-app

# The compiled assets sit outside /workspace/services/app, which dev bind-mounts over.
# settings.py serves them unless a host build in services/app/static/ overrides them.
COPY --from=assets /build/services/app/static /opt/assets
ENV ASSETS_DIR=/opt/assets

WORKDIR /workspace/services/app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
