# Template Monorepo

Full-stack monorepo with a React frontend and a Go API backed by PostgreSQL.

---

## Stack

- **Frontend Runtime & Package Manager**: [Bun](https://bun.sh/)
- **Backend Runtime**: [Go](https://go.dev/)
- **Database**: PostgreSQL via [pgx](https://github.com/jackc/pgx)

## Apps

- `apps/web` - [React 19](https://react.dev/) frontend with [Vite](https://vitejs.dev/) and [React Compiler](https://react.dev/learn/react-compiler)
- `apps/apis` - Go HTTP API with authentication

## Libraries

- `libs/ui` - Shared shadcn components, utilities, and styles

## Getting Started

### Prerequisites

- Bun >= 1.3.0
- Go >= 1.24
- PostgreSQL database

### Installation

```bash
bun install
```

### Environment Setup

```bash
cp .env.example .env
```

Update `.env` with your database connection string and other settings. This single file is used by all apps and libraries.

The database library applies its idempotent schema from `libs/database/schema.sql` when the API starts.

### Development

```bash
# PostgreSQL + API + web with live development processes
just dev

# Production containers spin up
just docker
```

Both commands run in the foreground and expose the web app at `http://localhost:3000` and API at `http://localhost:8000`.

`just docker` reads `.env` when present.

To stop detached services, use ctrl + c to terminate the shell where they were spun up or `devenv processes down` or `docker compose -f docker/docker-compose.yml down` respectively.

Individual processes remain available when needed:

```bash
# Run all development scripts without PostgreSQL
just apps
# or
bun dev

# Run specific app
just web
# or
bun --filter @template/web dev

just api
# or
bun --filter @template/api dev
```

### Devenv

With [devenv](https://devenv.sh/) installed, one command provisions Go and Bun, initializes a persistent PostgreSQL database, and starts PostgreSQL, the API, and the web app in readiness order:

```bash
just dev
# or
devenv up
```

PostgreSQL data is kept in devenv's project state. The API and web app remain available at `http://localhost:8000` and `http://localhost:3000`; the API and Web automatically reload when Go, schema files or frontend changes.

### Build

```bash
just build
# or
bun run build
```

TypeScript files are checked with:

```bash
just check
# or
bun run typecheck
```

### Lint & Format

```bash
# Check all files
just Lint
# or
bun check

# Format all files
just format
# or
bun format
```

## UI Components

Both `apps/web/components.json` and `libs/ui/components.json` use shadcn's monorepo routing. Run component commands against the app; reusable UI is written to `libs/ui` automatically:

```bash
bunx shadcn@latest add dialog
```

The shared Tailwind v4 theme lives at `libs/ui/src/styles/globals.css` and is imported by the web entrypoint.

## Auth

Authentication is implemented by the Go API with the following features:

- Bcrypt password hashing
- Signed HS256 JSON Web Tokens with configurable expiration
- Bearer-token authorization for protected endpoints
- Trusted-origin CORS enforcement

Set `JWT_SECRET` to a random value of at least 32 characters. See [`docs/authentication.md`](docs/authentication.md) for the request contract and security behavior.

## Routes

### Auth Routes

- `POST /api/auth/sign-in/email` - Sign in with email/password
- `POST /api/auth/sign-up/email` - Register with email/password
- `POST /api/auth/sign-out` - Complete client-side sign out
- `GET /api/auth/session` - Resolve the current bearer token to a user

### Protected Routes

- `GET /api/me` - Get current user info
