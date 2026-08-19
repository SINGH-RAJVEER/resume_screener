set dotenv-load := true
set shell := ["bash", "-cu"]

default:
    @just --list

# Start PostgreSQL, the Go API, and Vite through devenv.
dev:
    devenv up

# Build and start PostgreSQL, the Go API, and nginx through Docker Compose.
docker:
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}" docker compose -f docker/docker-compose.yml up --build --remove-orphans

# build the application
build:
    bun run build

# Run all development scripts without PostgreSQL
apps:
    bun dev

# Run web
web:
    bun --filter @template/web dev

# Run api
api:
    bun --filter @template/api dev

# Run tests
test:
    CGO_ENABLED=0 bun run test
# Typecheck TS files
check:
    bun run typecheck

# Run a pass of the linter
lint:
    bun check

# Run a pass of the formatter
format:
    bun format

