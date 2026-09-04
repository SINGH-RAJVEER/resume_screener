# SkillSignal

A resume screening tool with two sides that never mix. Candidates run private
checks on their own resumes and get a readiness score, suggestions, and a
corrected DOCX built only from facts their document actually contains.
Employers create roles, confirm the criteria that matter, upload or invite
resumes, and review ranked, evidence-cited evaluations against those criteria.

Every score traces back to quoted text from the source document. The model
stages, extraction and requirement assessment, run through OpenRouter with
strict JSON schemas, and their output is validated locally before anything is
stored. If no API key is configured, or a model call fails, everything falls
back to deterministic parsing and scoring. The system never lets a model erase
evidence that deterministic matching already found.

## Scope

What works today:

- Email auth with separate employer and candidate account types.
- Candidate private evaluations: PDF/DOCX/TXT upload, optional job description,
  scored report, suggestions, corrected resume download.
- Employer workspace: organizations with email-domain join policies, members
  with owner/recruiter/viewer roles, jobs with draft criteria extracted from
  descriptions, criteria confirmation into immutable versions, single and ZIP
  batch resume uploads, candidate invitations by link or passcode gated on an
  application window.
- Evaluations: deterministic skill matching against an O*NET-backed vocabulary,
  OpenRouter fact extraction and block embeddings for semantic evidence, with a
  content-hash cache so repeated blocks cost nothing, per-requirement
  assessment with cited evidence, weighted scores, hard-gate eligibility, CSV
  export with selectable columns.
- Points billing: ledgers for user and organization accounts, one free
  evaluation per calendar week for independent users, one-time Razorpay
  payments in INR, employer batch billing, and manually provisioned enterprise
  entitlements.
- Retention: resumes and everything derived from them expire after a
  configurable number of days. The API sweeps expired data on a schedule, and
  an operator can trigger a pass manually.
- Tracing and metrics through OpenTelemetry when an OTLP endpoint is set.

`POST /api/demo/session` seeds a pre-populated workspace and returns a token
for either a demo employer or a demo candidate.

What is not built yet: the employer review-decision screen, the full set of
cost and latency telemetry, calibration against labeled data, and the
remaining evaluation test suite. The specs in `docs/specs/` describe the full
intended product.

## Layout

```
apps/
	api/     Bun + Hono API service. Auth, organizations, jobs, uploads,
	         invitations, evaluation queries with evidence, CSV export,
	         billing with Razorpay reconciliation, admin retention, and demo
	         sessions. Runs Drizzle migrations at container start.
	worker/  Bun queue worker. Claims processing_job rows with FOR UPDATE SKIP
	         LOCKED, parses documents, matches skills against a corpus,
	         calls OpenRouter for extraction and assessment, stores
	         embeddings, settles point holds, renders the corrected DOCX.
	         Independent deployable; talks to Postgres and reads uploaded
	         files from shared storage.
	web/     React 19 + Vite frontend. Candidate portal and employer
	         workspace, shadcn-style UI components.
libs/
	ui/      Shared UI component package used by web.
	server-core/ Shared Bun database schema, configuration, billing, points,
	             retention, storage, and queue primitives.
docs/
	specs/       Product behavior, one file per area. The source of truth.
	research/    Provider constraints, architecture research.
```

Start the services locally with `bun run --cwd apps/api
dev` and `bun run --cwd apps/worker dev` after setting `JWT_SECRET` and
`DATABASE_URL`.

The worker's skill corpus (`apps/worker/src/domain/skills_corpus.json`)
is checked in.

## Run with Docker

Requires Docker and a `.env` file next to `docker-compose.yml` with:

```
POSTGRES_PASSWORD=change-me
JWT_SECRET=some-secret-at-least-32-characters-long
# optional, enables the model stages:
OPENROUTER_API_KEY=sk-or-...
# optional, enables Razorpay point packs and webhooks:
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
# optional, enables admin endpoints (retention sweep, enterprise provisioning):
ADMIN_TOKEN=some-admin-token
```

`.env.example` documents every variable with its default. Then:

```sh
docker compose up --build
```

The API container applies the Drizzle baseline migration on startup. When everything is up:
web at http://localhost:3000, API at http://localhost:8000 (health check at
`/health`). Uploaded files live in the `resume_storage` volume; the worker
mounts it read-write because it renders corrected resumes back into storage.

## Run locally

Assumes a running PostgreSQL server you can point at, plus
[bun](https://bun.sh).

1. Create a database, then export connection settings:

```sh
export DATABASE_URL="postgresql://postgres:password@localhost:5432/skillsignal"
export JWT_SECRET="some-secret-at-least-32-characters-long"
export STORAGE_ROOT=".local-storage"
export OPENROUTER_API_KEY="sk-or-..."   # optional
```

`.env.example` documents every variable with its default.

2. API, in one terminal:

```sh
cd apps/api
bun install
bun src/migrate.ts   # drizzle baseline, idempotent
bun dev        # bun on :8000 with reload
```

3. Worker, in a second terminal:

```sh
cd apps/worker
bun install
bun src/index.ts
```

4. Web, in a third terminal:

```sh
bun install    # once, from the repo root
cd apps/web
bun dev        # vite on :3000, expects the API on :8000
```

Sign up as an employer at `/sign-up` to reach the workspace, or as a
candidate to run private checks.

## Tests

```sh
cd apps/api && bun test
cd apps/worker && bun test
```

Or `bun test` at the repo root for both. The web app has no unit tests yet;
check it with `bun run typecheck` and `bun run lint`.

## Where to read more

`docs/specs/smart-resume-screener.md` is the product specification.
`docs/research/resume-screener-implementation.md` covers why the pipeline is
shaped this way: parser choices, OpenRouter routing and privacy settings,
scoring design, and the legal constraints around automated hiring tools.
