# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm
RUN useradd --create-home --no-log-init --uid 10001 app
# Named volumes seed ownership from the image mount point; the API writes
# uploaded resumes here as the non-root app user.
RUN mkdir -p /var/resume-storage && chown app:app /var/resume-storage
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --chown=app:app apps/api/app ./app
COPY --chown=app:app apps/api/alembic ./alembic
COPY --chown=app:app apps/api/alembic.ini ./alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
