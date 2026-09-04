# syntax=docker/dockerfile:1.7
FROM oven/bun:1.4.0 AS build
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/worker/package.json apps/worker/package.json
COPY libs/server-core/package.json libs/server-core/package.json
RUN bun install --frozen-lockfile
COPY apps/worker apps/worker
COPY libs/server-core libs/server-core
RUN bun run --cwd apps/worker build

FROM oven/bun:1.4.0-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app/apps/worker/dist ./dist
USER app
CMD ["bun", "dist/index.js"]
