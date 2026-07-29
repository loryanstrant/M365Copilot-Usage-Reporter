# Copilot instructions — M365 Copilot Usage Reporter (containerised)

These are standing rules for GitHub Copilot in this repository. Apply them to every suggestion.

## What this project is
A self-contained, containerised replacement for a Power Platform + Power BI solution. It ingests Microsoft 365
Copilot usage from Microsoft Graph (app-only / client credentials), stores it in PostgreSQL, computes metrics,
and serves a web dashboard. It runs anywhere via Docker and deploys to Azure Container Apps via `azd`.

## Stack (do not substitute without being asked)
- **Backend / engine:** Python 3.12, FastAPI, SQLAlchemy 2.x (typed, async), Alembic, httpx (async), MSAL,
  APScheduler, Pydantic v2 + pydantic-settings, psycopg (v3).
- **Database:** PostgreSQL 16. All schema changes go through Alembic migrations — never hand-edit tables.
- **Frontend:** React + Vite + TypeScript + Tailwind CSS. Charts: Recharts by default; ECharts for advanced
  visuals (streamgraph, sunburst, radar). FastAPI serves the built static bundle in production.
- **Packaging:** Docker + docker-compose (portable path). Deploy: `azd` + Bicep → Azure Container Apps.
- **Secrets:** encrypt at rest with Fernet (`cryptography`); read keys from env / Container Apps secrets.

## Terminology — MANDATORY
Microsoft Graph uses "session" and "interaction". This project renames them everywhere — in the database,
API, and UI. Never surface "session" or "interaction" to the user.
- Graph **session** (`sessionId`) → **Conversation** (`conversation_id`); distinct count is labelled **Conversations**.
- Graph **interaction** (interaction `id`) → **Prompt** (`prompt_id`); row count is labelled **Prompts**.
- "Avg Prompts per Conversation" (never "avg interactions per session").
Map Graph → project vocabulary at ingest time; the rest of the codebase only knows Conversations/Prompts.

## Microsoft Graph
- Auth: application (client-credentials) via MSAL. Config comes from the `app_config` table
  (tenant_id, client_id, client_secret decrypted with Fernet) — not hard-coded, not from static env.
- Required application permissions: `AiEnterpriseInteraction.Read.All`, `Directory.Read.All`.
- Copilot SKU id: `639dec6b-bb19-468b-871c-c5c441c4b0cb`. Treat the SKU list as **configurable**
  (`app_config.copilot_sku_ids`) — never assume a single hard-coded SKU in logic.
- Endpoints used:
  - Prompts: `GET /v1.0/copilot/users/{id}/interactionHistory/getAllEnterpriseInteractions?$filter=createdDateTime gt {since} and createdDateTime lt {until}&$top=100`
  - Licensed users: `GET /v1.0/users?$select=id,userPrincipalName,assignedLicenses&$filter=assignedLicenses/any(u:u/skuId eq {sku})`
  - License counts: `GET /v1.0/subscribedSkus`
  - Users + manager: `GET /v1.0/users?$select=...` and `GET /v1.0/users/{id}?$select=id&$expand=manager($select=id)`
- Always page via `@odata.nextLink`. Always honour `429` / `Retry-After` with exponential backoff.

## Ingest-time transforms (keep these exact rules)
- Strip prefix `IPM.SkypeTeams.Message.Copilot.` from app name.
- Drop rows where app == `M365AdminCenter`.
- `conversation_location` = "App" if conversationType contains "appchat", else "Chat".
- `chat_type`: bizchat→Work, webchat→Web, appClass `PrivateChat`→Temporary, else null.
- App-name normalisation: BizChat/WebChat/PrivateChat→"Copilot Chat"; VivaEngage→"Viva Engage";
  OfficeCopilotSearchAnswer→"Copilot Search".
- `teams_location` = text after the literal "Teams".
- entra_users: keep userType=="Member" AND accountEnabled==true; exclude UPN/mail containing
  `onmicrosoft.com`; mail must be non-empty; distinct by user_id.
- Keep transforms as **pure functions** with unit tests (small JSON fixtures). Metrics logic is deterministic
  SQL — cover it with tests against a seeded dataset so refactors can't silently change the numbers.

## Engine & backfill
- The ingestion worker is a normal async process — do NOT replicate the old Power Automate "child flow" split
  (that only existed to dodge Power Automate's parallel-loop variable bug). Use bounded concurrency
  (`asyncio.Semaphore`) instead.
- Upserts are idempotent on `prompt_id`. Persist per-user watermarks in `ingest_state`; every run writes a
  `job_runs` record with stats.
- Backfill is admin-configured (lookback) and **adaptive**: size batches/concurrency from licensed-user count,
  be throttle-aware (token bucket + Retry-After + back-pressure), resumable, cancellable, and report progress.

## Security & auth
- MVP: password gate (`app_users`, bcrypt) with roles `admin` / `viewer`. Protect all `/metrics/*` and `/admin/*`.
- Optional (feature-flagged): Entra ID OIDC; restrict report access to members of
  `app_config.report_access_group_id` (Graph `checkMemberGroups` / `memberOf`).
- The client secret is **write-only** from the UI, stored Fernet-encrypted, and never returned in a response.

## Conventions
- Async end-to-end (FastAPI async routes, async SQLAlchemy, httpx.AsyncClient).
- Type hints everywhere; Pydantic models for request/response schemas.
- Config via pydantic-settings; no secrets in code or committed env files (`.env` is git-ignored;
  keep `.env.example` current).
- Every code change must keep `docker compose up` working; add/adjust pytest as you go.
- Keep the repo layout: `/api`, `/worker`, `/shared`, `/frontend`, `/infra`, `/tests`.

## Don't
- Don't use the words "session" or "interaction" in UI copy, API field names, or DB columns.
- Don't hard-code tenant, client id/secret, or a single SKU in business logic.
- Don't return secrets to the client. Don't bypass Alembic. Don't add a different framework/ORM/chart lib
  without being asked.
