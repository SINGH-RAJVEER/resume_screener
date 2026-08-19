FROM oven/bun:1-alpine AS builder
WORKDIR /app

COPY package.json bun.lock* ./
COPY apps/api/package.json ./apps/api/
COPY apps/web/package.json ./apps/web/
COPY libs/ui/package.json ./libs/ui/
RUN bun install --frozen-lockfile

COPY tsconfig.base.json ./
COPY libs/ui ./libs/ui
COPY apps/web ./apps/web

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

WORKDIR /app/apps/web
RUN bun run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html

EXPOSE 80
