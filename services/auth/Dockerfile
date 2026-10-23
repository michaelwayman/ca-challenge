# Build context is the repo root (the uv workspace and shared lib live there).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /workspace

# Which shared library to build against: libs/shared (the working copy), or a tag exported
# under .build/ by `make up APP_SHARED=<tag>` / `AUTH_SHARED=<tag>`. Either way it lands at
# libs/shared in the image, the editable path uv.lock expects.
ARG SHARED_SRC=libs/shared

# Dependencies first so this layer caches until a manifest changes.
COPY pyproject.toml uv.lock .python-version ./
COPY ${SHARED_SRC}/pyproject.toml libs/shared/
COPY services/app/pyproject.toml services/app/
COPY services/auth/pyproject.toml services/auth/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package reviews-auth

# Then source. Workspace members install editable, so the library compose bind-mounts at
# libs/shared gives live edits in dev.
COPY ${SHARED_SRC} libs/shared
COPY services/auth services/auth
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reviews-auth

WORKDIR /workspace/services/auth
EXPOSE 8001
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
