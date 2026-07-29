# M365 Copilot Usage Reporter — Containerised MVP: Build Spec

Reverse-engineered from Loryan's Power Platform solution v2.5.2 + the "Avanoso" PBIP semantic model.

## 1. Data acquisition (the "engine") — Microsoft Graph, app-only (client credentials)

App registration (reuse existing or create): single-tenant, client secret.
Graph **application** permissions required:
- `AiEnterpriseInteraction.Read.All`  → Copilot interaction history
- `Directory.Read.All`                → users, managers, licenses

### Graph calls
1. **Copilot interactions (per licensed user, paged 100):**
   `GET /v1.0/copilot/users/{userId}/interactionHistory/getAllEnterpriseInteractions?$filter=createdDateTime gt {from} and createdDateTime lt {to}&$top=100`
   → follow `@odata.nextLink`. Each item: `id, sessionId, appClass, conversationType, createdDateTime, contexts[] (FileLocation/TeamsLocation)`.
2. **Currently Copilot-licensed users:**
   `GET /v1.0/users?$select=id,userPrincipalName,assignedLicenses&$filter=assignedLicenses/any(u:u/skuId eq 639dec6b-bb19-468b-871c-c5c441c4b0cb)`
   (SKU `639dec6b-…` = Microsoft 365 Copilot. Make this SKU list configurable.)
3. **License totals (time series):** `GET /v1.0/subscribedSkus` → filter to Copilot SKU; record `prepaidUnits.enabled`, `consumedUnits`, `suspended/warning/lockedOut`, `capabilityStatus`, timestamp.
4. **Entra users + manager:** page `GET /v1.0/users?$select=id,userPrincipalName,mail,userType,jobTitle,companyName,department,officeLocation,country,displayName,accountEnabled,assignedLicenses,onPremisesExtensionAttributes`
   then per user `GET /v1.0/users/{id}?$select=id&$expand=manager($select=id)`.

### Engine optimisation vs the original Power Automate design
The original used CHILD flows for the interaction retriever purely because Power Automate overwrote
variables in parallel loops. In a real worker this constraint disappears. Design:
- Async worker (bounded concurrency, e.g. semaphore of 10–20) iterating licensed users.
- Per-user incremental window: pull only since `last_success_watermark` (store per user); default backfill window configurable (e.g. 30 days on first run).
- Idempotent **upsert on `interaction_id`** (natural de-dupe; safe re-runs).
- Respect Graph throttling: honour `Retry-After` on 429; exponential backoff.
- Checkpoint per user so a failure doesn't lose the whole run.
- Runs: daily interactions + licensed users + license count; weekly Entra users/managers. Scheduler in-process or separate cron container.

## 2. Data model (PostgreSQL) — parsed at ingest (push transforms out of the report)

**interactions** (one row per interaction; from `getAllEnterpriseInteractions`)
- interaction_id (PK, text), user_id (text, idx), session_id (text, idx), app_name (text),
  interaction_date (date, idx), conversation_type (text), interaction_location (text: App|Chat),
  chat_type (text: Work|Web|Temporary|null), file_location (text), teams_location (text),
  raw_json (jsonb), ingested_at (timestamptz)

Ingest-time transforms (from the Power Query M):
- Strip prefix `IPM.SkypeTeams.Message.Copilot.` from `appClass`.
- Drop rows where app == `M365AdminCenter`.
- `interaction_location` = "App" if conversationType contains "appchat" else "Chat".
- `chat_type` = bizchat→Work, webchat→Web, appClass==PrivateChat→Temporary, else null.
- App name normalisation: BizChat→"Copilot Chat", WebChat→"Copilot Chat", PrivateChat→"Copilot Chat",
  VivaEngage→"Viva Engage", OfficeCopilotSearchAnswer→"Copilot Search".
- teams_location = text after the literal "Teams" delimiter.

**entra_users**
- user_id (PK), upn, email, display_name (User Name), job_title, company_name, department,
  office_location, country, manager_id, account_enabled (bool), user_type, has_copilot_license (bool),
  extension_attribute_1..15, updated_at
- Filters at ingest: userType == "Member", accountEnabled == true, exclude UPN/mail containing
  `onmicrosoft.com`, mail not null/empty, distinct by user_id.
- Manager fields (name/dept/office/country/company/upn/email) resolved by self-join on manager_id (do in SQL/view, not stored).

**licensed_users** (current Copilot-licensed snapshot): user_id (PK), captured_at.

**license_counts** (time series): id, recorded_date (date), status, enabled (int), allocated/consumedUnits (int),
  available (= enabled − allocated), suspended, warning, locked_out.

**app_config** (admin-entered settings; secret encrypted): tenant_id, client_id, client_secret_encrypted,
  copilot_sku_ids (text[]), report_access_group_id (Entra security group), backfill_days, schedule_cron, updated_at, updated_by.

**ingest_state**: per-user watermark + per-job last run/status for observability.

**app_users / sessions** (for the password gate + optional local accounts): id, username, password_hash, role, created_at.

## 3. Metrics (compute in SQL/API — recreate the DAX)

Core (from CopilotInteractions / Measures Table / DailyInteractionSummary):
- Interactions = count(interaction_id); Sessions = distinct(session_id).
- Avg interactions per session = interactions / sessions (overall, per user, per app, per user-per-app).
- Per **user**: earliest interaction date, last interaction date, days since earliest, days since last usage, sessions, interactions, avg/session.
- Per **app**: same set + days since last usage.
- Avg interactions/sessions per user per app (combined).
- **DailyInteractionSummary**: count by (app_name, interaction_date) → trend lines.
- **InteractionCategories** (trailing 30 days per user): 0 / <10 / 10–50 / 50–100 / >100 buckets.
- **CopilotScore**: tiered score from daily interaction volume (SWITCH ladder; keep configurable thresholds).
- **Active vs inactive**: active = interaction in last 30 days; inactive/laggards = licensed but no recent usage.
- **HasCopilotLicense** join (entra_users ⋈ licensed_users).
- **Licenses over time**: enabled vs allocated vs available by recorded_date.

## 4. Reporting UI (recreate Loryan's report, prettier; not size-constrained)

Polished pages to build (ignore the "TEST -" experimental pages):
- **Home / Overview**: KPI cards (total interactions, sessions, active users, licensed users, avg/session, CopilotScore),
  interactions trend, usage-by-app breakdown, active-vs-inactive donut.
- **Usage by app**: per-app interactions, sessions, avg/session, users, first/last usage, trend.
- **Usage by user**: per-user table + drill: interactions, sessions, avg/session, first/last, days-since-last, license flag, manager/department.
- **Leaderboards**: top users by interactions/sessions (with dept/manager context).
- **Laggardboards / Inactive**: licensed users with zero/low/no recent usage (drillthrough to user).
- **Interaction Count by Category**: 30-day bucket distribution.
- **Licenses over time**: enabled/allocated/available trend.
- **About**: data freshness, last ingest run, methodology notes.

Cross-cutting: global date-range filter, app filter, department/manager/office filters, search, CSV export.

## 5. Auth
- MVP: session password gate (local `app_users`, hashed). Admin role required for the Settings/admin page.
- Optional (toggle): Entra ID OIDC sign-in; restrict report access to members of `report_access_group_id`
  (check group membership via Graph `checkMemberGroups`/`memberOf` at login).

## 6. Admin / installer interface (secure)
Settings page (admin-only) to enter, persisted to `app_config` (secret encrypted at rest):
- Tenant ID, Client ID, Client Secret (write-only field), Copilot SKU IDs, backfill days, schedule.
- Entra security **group ID** whose members may view the report.
- "Test connection" button (validates Graph auth + permissions). "Run ingest now" button.
- Show last run status/watermarks. No redeploy needed to configure.

## 7. Packaging & deploy (portable, ~1-click, single resource group)
- Dockerfiles for **api/web** and **worker**; `docker-compose.yml` (api + worker + postgres + volume) → runs anywhere (localhost, any Docker host, another cloud). This is the portability guarantee.
- Azure: `azd` template (azure.yaml + infra Bicep) → **Azure Container Apps** (api/web + worker) into a single resource group; `azd up` ≈ 1-click; `azd down` to tear down; redeployable to any subscription.
- DB for MVP: containerised Postgres with a persistent volume (keeps everything self-contained & movable). Documented upgrade path: swap `DATABASE_URL` to **Azure Database for PostgreSQL Flexible Server** for production scale — no code change.
- Config via env vars / Container Apps secrets; app_config table holds the Graph creds entered via admin UI.
- One-command local dev: `docker compose up`.

## Recommended stack (fastest-to-MVP + scales + prettiest UI)
- Backend/engine: **Python 3.12 + FastAPI + SQLAlchemy + httpx (async) + msal + APScheduler**.
- DB: **PostgreSQL 16**.
- Frontend: **React + Vite + TypeScript + Tailwind + a chart/UI kit (Tremor or shadcn/ui + Recharts/ECharts)**; built static, served by the API (single web container).
- Secret encryption: Fernet (cryptography) with a key from env/Key Vault.
- Deploy: **azd + Bicep → Azure Container Apps**; portable via docker-compose.

## Repo layout (proposed)
```
/api            FastAPI app (routes, auth, metrics SQL, serves built frontend)
/worker         ingestion engine (Graph client, transforms, scheduler)
/shared         SQLAlchemy models, config, db, crypto
/frontend       React app (pages, components, charts)
/infra          Bicep + azure.yaml (azd)
docker-compose.yml
.env.example
README.md
```
