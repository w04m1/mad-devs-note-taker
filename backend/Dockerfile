# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# The backend workstream owns pyproject.toml and uv.lock at this context root.
# Copying the whole context first tolerates package code under app/ and Alembic
# files at the root without encoding a more specific parallel-branch layout.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "--frozen", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
