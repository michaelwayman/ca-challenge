# Build context is the repo root (the uv workspace and shared lib live there).
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
COPY libs/ca_authlib/pyproject.toml libs/ca_authlib/
COPY services/app/pyproject.toml services/app/
COPY services/auth/pyproject.toml services/auth/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package reviews-auth

# Then source. Workspace members install editable, so a bind-mounted ./libs
# gives live edits to the shared lib in dev.
COPY libs/ca_authlib libs/ca_authlib
COPY services/auth services/auth
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reviews-auth

WORKDIR /workspace/services/auth
EXPOSE 8001
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
