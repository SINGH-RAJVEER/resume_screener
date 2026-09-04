# syntax=docker/dockerfile:1.7
FROM oven/bun:1.4.0 AS build
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/api/package.json apps/api/package.json
COPY libs/server-core/package.json libs/server-core/package.json
RUN bun install --frozen-lockfile
COPY apps/api apps/api
COPY libs/server-core libs/server-core
RUN bun run --cwd apps/api build

FROM oven/bun:1.4.0-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app/apps/api/dist ./dist
COPY --from=build --chown=app:app /app/libs/server-core/drizzle ./drizzle
USER app
EXPOSE 8000
CMD ["sh", "-c", "bun dist/migrate.js && exec bun dist/index.js"]
