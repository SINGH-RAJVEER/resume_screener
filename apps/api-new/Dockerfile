# syntax=docker/dockerfile:1.7
FROM oven/bun:1.4.0 AS build
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/api-new/package.json apps/api-new/package.json
COPY libs/server-core/package.json libs/server-core/package.json
RUN bun install --frozen-lockfile
COPY apps/api-new apps/api-new
COPY libs/server-core libs/server-core
RUN bun run --cwd apps/api-new build

FROM oven/bun:1.4.0-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app/apps/api-new/dist ./dist
USER app
EXPOSE 8000
CMD ["bun", "dist/index.js"]
