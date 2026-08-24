# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm
RUN useradd --create-home --no-log-init --uid 10001 app
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --chown=app:app apps/worker/worker ./worker
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
CMD ["python", "-m", "worker.main"]