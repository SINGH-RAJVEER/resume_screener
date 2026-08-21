FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.13-slim-bookworm AS builder
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm
RUN useradd --create-home app
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --chown=app:app apps/worker/worker ./worker
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
CMD ["python", "-m", "worker.main"]