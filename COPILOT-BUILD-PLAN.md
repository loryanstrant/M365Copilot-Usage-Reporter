# M365 Copilot Usage Reporter — Containerised MVP
## Build plan + GitHub Copilot prompts (VS Code)

This is your working document. Each **Phase** has: what it delivers, and a **ready-to-paste prompt**
for GitHub Copilot (Agent mode in VS Code). Do them in order — later prompts assume earlier output exists.

---

## 0. Context to give Copilot ONCE (paste this first, as a "project brief")

> We are building a self-contained, containerised replacement for a Power Platform + Power BI solution
> called the **M365 Copilot Usage Reporter**. It ingests Microsoft 365 Copilot usage from Microsoft Graph
> (app-only / client credentials), stores it in PostgreSQL, and serves a web dashboard.
>
> **Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, httpx (async), MSAL, APScheduler, PostgreSQL 16,
> Pydantic v2. Frontend: React + Vite + TypeScript + Tailwind + Recharts (+ ECharts for advanced visuals).
> Packaged with Docker + docker-compose; deployed to Azure Container Apps via `azd` (Bicep).
>
> **Terminology (IMPORTANT):** Microsoft Graph calls them `sessionId` and interaction records. In OUR
> schema, API, and UI we rename them:
> - a Graph **session** → **Conversation** (`conversation_id`; distinct count = "Conversations")
> - a Graph **interaction** → **Prompt** (`prompt_id`; row count = "Prompts")
> Never surface the words "session" or "interaction" in the UI. Map them at ingest.
>
> **Graph app permissions (application):** `AiEnterpriseInteraction.Read.All`, `Directory.Read.All`.
> **Copilot SKU id:** `639dec6b-bb19-468b-871c-c5c441c4b0cb` (make the SKU list configurable).
>
> Build incrementally. After each phase, ensure `docker compose up` works and add/adjust tests.

---

## Repo layout (target)
```
/api            FastAPI: routes, auth, metrics, serves built frontend
/worker         ingestion engine: Graph client, transforms, scheduler, backfill
/shared         SQLAlchemy models, db session, config, crypto (shared by api+worker)
/frontend       React + Vite app
/infra          Bicep + azure.yaml (azd)
/tests          pytest
docker-compose.yml
.env.example
README.md
```

---

## Terminology & app-name mapping (use everywhere)
| Graph / original | This project |
|---|---|
| session / sessionId | **Conversation** / conversation_id |
| interaction / interaction id | **Prompt** / prompt_id |
| appClass `IPM.SkypeTeams.Message.Copilot.*` | strip prefix |
| `BizChat`, `WebChat`, `PrivateChat` | **Copilot Chat** |
| `VivaEngage` | **Viva Engage** |
| `OfficeCopilotSearchAnswer` | **Copilot Search** |
| app == `M365AdminCenter` | drop row |
| conversationType contains `appchat` | Conversation Location = **App** (else **Chat**) |
| `bizchat`→Work, `webchat`→Web, appClass `PrivateChat`→Temporary | **Chat Type** |

---

## Phase 0 — Scaffold & docker-compose

**Delivers:** monorepo skeleton, `docker-compose.yml` (api + worker + postgres + volume), `.env.example`,
FastAPI `/health`, shared config/db modules, hot-reload dev.

**Copilot prompt:**
> Scaffold the repo per the layout in the project brief. Create:
> - `pyproject.toml` (or requirements) for a shared Python env: fastapi, uvicorn[standard], sqlalchemy>=2,
>   alembic, httpx, msal, apscheduler, pydantic>=2, pydantic-settings, psycopg[binary], cryptography, python-jose[cryptography], passlib[bcrypt], pytest, pytest-asyncio.
> - `/shared/config.py` using pydantic-settings reading `DATABASE_URL`, `SECRET_KEY`, `FERNET_KEY`, etc.
> - `/shared/db.py` async SQLAlchemy engine + session factory.
> - `/api/main.py` FastAPI app with `/health` returning db connectivity.
> - `/worker/main.py` placeholder entrypoint that logs and idles.
> - `Dockerfile` for api and for worker; `docker-compose.yml` with services: `db` (postgres:16, volume
>   `pgdata`, healthcheck), `api` (depends_on db healthy, ports 8000), `worker` (depends_on db). Mount source for dev.
> - `.env.example` and a `README.md` quickstart (`docker compose up`).
> Verify `docker compose up` starts all three and `/health` returns 200.

---

## Phase 1 — Database schema & models

**Delivers:** SQLAlchemy models + first Alembic migration for all tables (using the new vocabulary).

**Copilot prompt:**
> In `/shared/models.py` create SQLAlchemy 2.0 models and an Alembic migration for these tables. Use the
> Conversations/Prompts vocabulary.
>
> **prompts** — one row per Copilot prompt:
> `prompt_id` (PK, text), `user_id` (text, index), `conversation_id` (text, index), `app_name` (text),
> `prompt_date` (date, index), `conversation_type` (text), `conversation_location` (text: App|Chat),
> `chat_type` (text: Work|Web|Temporary|null), `file_location` (text), `teams_location` (text),
> `raw_json` (JSONB), `ingested_at` (timestamptz default now).
>
> **entra_users** — `user_id` (PK), `upn`, `email`, `display_name`, `job_title`, `company_name`,
> `department`, `office_location`, `country`, `manager_id` (index), `account_enabled` (bool),
> `user_type`, `has_copilot_license` (bool), `extension_attribute_1..15` (text), `updated_at`.
>
> **licensed_users** — `user_id` (PK), `captured_at` (timestamptz).
>
> **license_counts** — `id` (PK), `recorded_date` (date, index), `status`, `enabled` (int),
> `allocated` (int), `available` (int), `suspended` (int), `warning` (int), `locked_out` (int).
>
> **app_config** — single-row settings: `id` (PK=1), `tenant_id`, `client_id`,
> `client_secret_encrypted` (bytea/text), `copilot_sku_ids` (text[]), `report_access_group_id` (text),
> `backfill_days` (int default 30), `schedule_cron` (text), `updated_at`, `updated_by`.
>
> **ingest_state** — `key` (PK, e.g. 'user:{id}:prompts'), `watermark` (timestamptz), `last_status`,
> `last_run_at`, `detail` (JSONB). Also a `job_runs` table: `id`, `job_name`, `started_at`, `finished_at`,
> `status`, `stats` (JSONB) for observability.
>
> **app_users** — `id` (PK), `username` (unique), `password_hash`, `role` (admin|viewer), `created_at`.
>
> Wire Alembic (`alembic init`, env.py using `DATABASE_URL`), generate the initial migration, and make the
> api run migrations on startup (or a `make migrate`). Add a `scripts/seed_admin.py` to create the first admin.

---

## Phase 2 — Graph client & transforms

**Delivers:** app-only MSAL token, async httpx Graph client for the 4 data pulls, and pure transform
functions that turn raw Graph JSON into the `prompts`/`entra_users`/`license_counts` shapes.

**Copilot prompt:**
> In `/worker/graph.py` build an async Microsoft Graph client using MSAL client-credentials (tenant_id,
> client_id, client_secret from `app_config`, secret decrypted with Fernet). Implement, all with paging via
> `@odata.nextLink`, 429/Retry-After handling, and exponential backoff:
> 1. `get_copilot_prompts(user_id, since, until)` →
>    `GET /v1.0/copilot/users/{user_id}/interactionHistory/getAllEnterpriseInteractions?$filter=createdDateTime gt {since} and createdDateTime lt {until}&$top=100`
> 2. `get_licensed_users(sku_ids)` →
>    `GET /v1.0/users?$select=id,userPrincipalName,assignedLicenses&$filter=assignedLicenses/any(u:u/skuId eq {sku})`
> 3. `get_subscribed_skus()` → `GET /v1.0/subscribedSkus` (filter to configured Copilot SKUs).
> 4. `get_entra_users()` → page `GET /v1.0/users?$select=id,userPrincipalName,mail,userType,jobTitle,companyName,department,officeLocation,country,displayName,accountEnabled,assignedLicenses,onPremisesExtensionAttributes`
>    and `get_manager(user_id)` → `GET /v1.0/users/{id}?$select=id&$expand=manager($select=id)`.
>
> In `/worker/transforms.py` write pure functions (with unit tests) that mirror the original Power Query:
> - **prompt transform:** flatten each interaction to a prompt row; map `sessionId`→conversation_id,
>   `id`→prompt_id, `appClass`→app_name; strip prefix `IPM.SkypeTeams.Message.Copilot.`; drop
>   `M365AdminCenter`; `conversation_location` = "App" if conversationType contains "appchat" else "Chat";
>   `chat_type` = bizchat→Work, webchat→Web, appClass PrivateChat→Temporary, else null; app-name
>   normalisation (BizChat/WebChat/PrivateChat→"Copilot Chat", VivaEngage→"Viva Engage",
>   OfficeCopilotSearchAnswer→"Copilot Search"); `teams_location` = text after "Teams"; `prompt_date` = date of createdDateTime.
> - **entra_users transform:** keep userType=="Member" AND accountEnabled==true; exclude UPN/mail containing
>   `onmicrosoft.com`; mail not null/empty; distinct by user_id; flatten manager id; keep extensionAttributes 1..15.
> - **license_counts transform:** from subscribedSkus record enabled/consumed(allocated)/suspended/warning/
>   lockedOut/status; `available` = enabled − allocated; stamp recorded_date.
> Add pytest cases using small JSON fixtures.

---

## Phase 3 — Ingestion engine + scheduler

**Delivers:** the async worker that runs the pulls, upserts idempotently, tracks watermarks, and schedules
daily/weekly jobs. This replaces the 8 Power Automate flows (the child-flow split is no longer needed).

**Copilot prompt:**
> In `/worker/ingest.py` implement the ingestion engine (async, `httpx.AsyncClient`, bounded concurrency via
> `asyncio.Semaphore`, default 15). Jobs:
> - `sync_licensed_users()` — refresh `licensed_users` (full replace) + set `entra_users.has_copilot_license`.
> - `sync_prompts()` — for each licensed user, read `ingest_state` watermark; pull prompts from watermark→now
>   (first run: now − `backfill_days`); transform; **upsert on `prompt_id`**; advance watermark; record per-user
>   status; checkpoint so partial failures don't lose progress.
> - `sync_license_counts()` — append a `license_counts` snapshot (idempotent per day).
> - `sync_entra_users()` — refresh users + managers (weekly).
> Wrap each run in a `job_runs` record with stats (users processed, prompts upserted, errors, duration).
> Add APScheduler in `/worker/scheduler.py`: `sync_prompts` + `sync_licensed_users` + `sync_license_counts`
> daily (cron from `app_config.schedule_cron`), `sync_entra_users` weekly. Expose an internal trigger the API
> can call ("Run now"). Make everything re-runnable and safe to retry.

---

## Phase 4 — Smart backfill (admin-configurable, throttle-aware)

**Delivers:** a one-off historical backfill that the admin controls (how far back), which **adaptively batches
by licensed-user count** so large tenants don't get throttled by Graph — resumable, with live progress.

**Copilot prompt:**
> Add `/worker/backfill.py` implementing an intelligent historical backfill, controlled from the admin UI.
> Inputs: `lookback` (days or months) and optional `app` filter. Behaviour:
> - Determine licensed-user count `N` and compute a **plan** before running: split the time range into
>   windows (e.g. monthly chunks) × user batches. Choose batch size & concurrency adaptively from `N`
>   (e.g. small tenants run wide/fast; thousands of users → smaller waves, lower concurrency, inter-batch
>   delay) and expose the estimated total Graph calls + rough ETA.
> - **Adaptive rate limiting:** token-bucket + strict `Retry-After` honouring; on repeated 429s automatically
>   reduce concurrency and increase delay (back-pressure); ramp back up when clear.
> - **Resumable & idempotent:** persist progress per (user, window) in `ingest_state`/`job_runs`; upsert on
>   `prompt_id`; a re-run resumes where it left off; a "cancel" stops cleanly.
> - Run as a background task; publish progress (windows done/total, users done/total, prompts ingested,
>   current throttle state, ETA) queryable by the API for a progress bar.
> Add an API route `POST /admin/backfill` (admin only) to start it with `{lookback}`, `GET /admin/backfill/status`
> to poll, and `POST /admin/backfill/cancel`. Unit-test the planner (batch sizing for N=5, N=500, N=5000).

---

## Phase 5 — Metrics API (recreate the DAX in SQL)

**Delivers:** FastAPI endpoints computing every metric from the original report, renamed to Conversations/Prompts.
Prefer SQL views/materialised views for speed.

**Metric definitions to implement (from the original DAX):**
- **Prompts** = COUNT(prompt_id). **Conversations** = COUNT(DISTINCT conversation_id).
- **Avg Prompts per Conversation** = Prompts / Conversations (overall, per user, per app, per user×app).
- **Per user:** earliest prompt date, last prompt date, days since earliest, **days since last usage**,
  Conversations, Prompts, avg prompts/conversation.
- **Per app:** same set incl. days since last usage; **users per app**; avg prompts & conversations per user per app.
- **Daily summary:** Prompts by (app_name, prompt_date) → trends.
- **Prompt categories (trailing 30 days per user):** buckets `0`, `<10`, `10–50`, `50–100`, `>100`.
- **CopilotScore:** tiered score from daily prompt volume (keep the SWITCH ladder; make thresholds config).
- **Active vs inactive:** active = a prompt in last 30 days; **laggards/inactive** = licensed but no recent usage.
- **Has Copilot license** = user_id present in `licensed_users`.
- **Licenses over time:** enabled vs allocated vs available by recorded_date.
- **Org rollups:** by department / manager / office / company (for leaderboards & laggardboards).

**Copilot prompt:**
> In `/api/metrics.py` (+ SQL views in a migration) implement read endpoints returning JSON for the dashboard,
> using the Conversations/Prompts vocabulary and honouring query filters `from`, `to`, `app`, `department`,
> `manager`, `office`, `search`. Implement:
> - `GET /metrics/overview` — KPI cards: total Prompts, Conversations, active users (30d), licensed users,
>   avg Prompts/Conversation, CopilotScore; plus prompts trend, usage-by-app, conversation-location split,
>   active-vs-inactive.
> - `GET /metrics/by-app`, `GET /metrics/by-user` (with per-user first/last, days-since-last, license flag,
>   department/manager), `GET /metrics/leaderboards`, `GET /metrics/laggards` (licensed + inactive),
>   `GET /metrics/prompt-categories`, `GET /metrics/locations` (chat types / teams locations / file locations
>   trends), `GET /metrics/licenses-over-time`, `GET /metrics/data-freshness` (last job_runs).
> Build SQL views for the heavy aggregations; add `GET /export/{dataset}.csv`. Add pytest against seeded data.

---

## Phase 6 — Auth & secure admin

**Delivers:** password gate with roles (MVP), optional Entra ID OIDC with **security-group-gated** access, and
the secure **admin settings** page backend.

**Copilot prompt:**
> Implement auth in `/api/auth.py`:
> - **MVP password gate:** `POST /auth/login` (username/password from `app_users`, bcrypt), issue a signed
>   session cookie/JWT; `role` in (admin, viewer); dependency `require_admin`. Protect all `/metrics/*` and
>   `/admin/*`.
> - **Optional Entra ID OIDC (feature-flagged):** authorization-code login against the configured tenant;
>   on callback, resolve the user's group membership and **allow only members of
>   `app_config.report_access_group_id`** (use Graph `checkMemberGroups` or `memberOf`); map to viewer, and a
>   configurable admin group to admin. Fall back to password gate when the flag is off.
> - **Secure admin settings backend:** `GET/PUT /admin/config` (admin only) to set tenant_id, client_id,
>   client_secret (write-only; store Fernet-encrypted), copilot_sku_ids, report_access_group_id, backfill_days,
>   schedule_cron. `POST /admin/test-connection` validates Graph auth + that both app permissions resolve.
>   `POST /admin/run-now` triggers ingestion. Never return the secret in plaintext.

---

## Phase 7 — React dashboard (recreate the report, prettier)

**Delivers:** the web UI — polished versions of the real report pages, plus the worthwhile visuals rescued from
the TEST pages, plus the admin console.

**Pages to build (final list):**
1. **Overview / Home** — KPI cards, Prompts trend, usage-by-app, conversation-location split, active-vs-inactive donut.
2. **Usage by app** — per-app Prompts/Conversations/avg/users/first-last; trend; **small-multiples trend grid** (rescued from "TEST - Usage trends").
3. **Usage by user** — sortable table + drill: Prompts, Conversations, avg, first/last, days-since-last, license, dept/manager.
4. **Leaderboards** — top users; top departments/offices/managers.
5. **Laggardboards / Inactive** — licensed but no/low recent usage; drillthrough to user.
6. **Prompt Count by Category** — 30-day bucket distribution.
7. **Where Copilot is used (Locations)** — chat types / Teams locations / File locations, as **streamgraph + stacked area + pie** (rescued from "TEST - Conversation location trends"); plus a **Sunburst** (app→chat type / department→app) rescued from "TEST - Other visuals").
8. **Licenses over time** — enabled/allocated/available trend.
9. **Usage profiles (Radar)** — optional: radar comparison of app usage across departments/users (rescued from "TEST - Radar Charts").
10. **About / Data freshness** — sources, last refresh, methodology.
11. **Admin console** — settings form (app-reg values, SKU ids, access group id, schedule), Test connection,
    Run now, **Backfill** control with lookback picker + live progress bar, job history.

**Copilot prompt:**
> Build the frontend in `/frontend` (Vite + React + TS + Tailwind + Recharts; add ECharts for streamgraph,
> sunburst, radar). Create an app shell with left-nav, a global filter bar (date range, app, department,
> manager, office, search) that drives all queries, and a login screen. Use the Conversations/Prompts wording
> throughout (never "session"/"interaction"). Implement the pages listed in Phase 7 against the `/metrics/*`
> endpoints, each with loading/empty states and CSV export where a table exists. Make it clean and modern
> (cards, soft shadows, a coherent palette, dark-mode optional) — we are not constrained by Power BI's layout.
> Build the **Admin console** against `/admin/*`: settings form (client secret write-only), Test connection,
> Run now, and a Backfill panel with a lookback selector that calls `POST /admin/backfill`, then polls
> `/admin/backfill/status` to render a progress bar (windows/users done, prompts ingested, throttle state, ETA)
> with a Cancel button. Have FastAPI serve the built static files in production.

---

## Phase 8 — Deploy (portable + near 1-click)

**Delivers:** docker-compose for anywhere, and an `azd` template that stands the whole thing up in a single
Azure resource group and can be torn down / moved to another subscription.

**Copilot prompt:**
> Add deployment. 1) Finalise `docker-compose.yml` (api, worker, db + volume) as the portable path — one command
> `docker compose up` runs the full stack anywhere; document swapping `DATABASE_URL` to Azure Database for
> PostgreSQL Flexible Server for production. 2) Create `/infra` Bicep + `azure.yaml` for **Azure Developer CLI
> (`azd`)** that provisions, in a **single resource group**: Container Apps environment, a container app for
> `api` (ingress external) and one for `worker` (no ingress), plus either a containerised Postgres or (preferred)
> Azure Database for PostgreSQL Flexible Server, and stores secrets as Container Apps secrets. `azd up` should
> deploy end-to-end and print the app URL; `azd down` removes everything. Keep everything parameterised so it
> redeploys cleanly into another subscription. Update `README.md` with both paths (local compose + `azd up`),
> first-run steps (seed admin → open Admin console → enter app-reg values → Test connection → set backfill →
> Run now).

---

## First-run checklist (put in README)
1. `docker compose up` (or `azd up`).
2. `python scripts/seed_admin.py` → create the first admin login.
3. Sign in → **Admin console** → enter Tenant ID, Client ID, Client Secret, confirm Copilot SKU id(s),
   set the **report access security-group ID**, choose schedule + backfill window.
4. **Test connection** → **Run now** (or start **Backfill**) → watch progress.
5. Open the dashboard.

## Notes / gotchas
- Graph `getAllEnterpriseInteractions` is the sanctioned Copilot interaction-history API; it pages and throttles
  — the adaptive backfill exists specifically for large tenants.
- Keep the Copilot **SKU id list** configurable (SKUs change; multiple Copilot SKUs may apply).
- Store the client secret **encrypted at rest** (Fernet) and never return it to the UI.
- The whole metrics layer is deterministic SQL — add unit tests with a small seeded dataset so a refactor
  can't silently change the numbers.
