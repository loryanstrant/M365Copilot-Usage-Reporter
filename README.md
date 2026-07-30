# M365 Copilot Usage Reporter (containerised)

A self-contained, containerised replacement for a Power Platform + Power BI solution. It ingests
Microsoft 365 Copilot usage from Microsoft Graph (app-only / client credentials), stores it in
PostgreSQL, computes metrics, and serves a web dashboard. Runs anywhere via Docker and deploys to
Azure Container Apps.

## Deploy to Azure (one click)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Usage-Reporter%2Fmain%2Finfra%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Usage-Reporter%2Fmain%2Finfra%2FcreateUiDefinition.json)

The button provisions everything into a resource group of your choice: a PostgreSQL flexible
server, a Container Apps environment, and the **api** + **worker** container apps (pulled as
prebuilt public images from GitHub Container Registry). You only enter an **admin password** — the
database password and encryption keys are generated for you. When the deployment finishes, open the
`dashboardUrl` output, sign in, and complete the in-app **Settings** to connect Microsoft Graph.

> **Maintainers:** the button relies on public images. After the first run of the
> **Publish container images** workflow, set both GHCR packages
> (`m365copilot-usage-reporter/api` and `.../worker`) to **Public** once, so Container Apps can pull
> them anonymously. See [`docs/deploy.md`](docs/deploy.md) for the full walkthrough.

## Terminology

Microsoft Graph uses "session" and "interaction". This project renames them everywhere:

| Microsoft Graph        | This project                    |
| ---------------------- | ------------------------------- |
| session / `sessionId`  | **Conversation** / `conversation_id` (count = **Conversations**) |
| interaction / `id`     | **Prompt** / `prompt_id` (count = **Prompts**) |

The words "session" and "interaction" never appear in the API, database, or UI.

## Stack

- **Backend / engine:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, httpx, MSAL,
  APScheduler, Pydantic v2, psycopg v3.
- **Database:** PostgreSQL 16 (schema via Alembic).
- **Frontend:** React + Vite + TypeScript + Tailwind + Recharts (ECharts for advanced visuals).
- **Packaging:** Docker + docker-compose. Deploy: `azd` + Bicep → Azure Container Apps.

## Repo layout

```
/api         FastAPI: routes, auth, metrics, serves built frontend
/worker      ingestion engine: Graph client, transforms, scheduler, backfill
/shared      SQLAlchemy models, db session, config, crypto (shared by api+worker)
/frontend    React + Vite app
/infra       Bicep + azure.yaml (azd)
/tests       pytest
docker-compose.yml
.env.example
```

## Quick start (local)

```powershell
# 1. Create your env file and a Fernet key
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the printed value into FERNET_KEY in .env

# 2. Start the full stack (api + worker + postgres + frontend)
docker compose up --build
```

- **Dashboard (web UI):** http://localhost:5173
- **API + Swagger docs:** http://localhost:8000/docs
- **API health check:** http://localhost:8000/health
- **Postgres:** localhost:5432 (user/pass/db all `copilot` by default)

On first start an admin login is seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD`
in `.env` (defaults `admin` / `change-me` — change these). Sign in at the
dashboard, open **Settings**, enter your Graph credentials, **Test connection**,
then **Run ingest now** (or **Run backfill** for history).

## Features

- **Overview** — KPI cards (Prompts, Conversations, avg prompts/conversation,
  adoption) plus trend, active-vs-inactive, and usage-by-app charts.
- **Usage** — per-app and per-user tables (CSV export) + engagement buckets.
- **Leaderboards** — top users by prompts and conversations.
- **Licenses** — enabled/allocated/available over time.
- **About** — data freshness + methodology.
- **Settings (admin)** — Graph config (secret write-only, Fernet-encrypted),
  test connection, run ingest, resumable **backfill** with live progress.
- Global date-range/app **filters**, **CSV export**, and a **light/dark** theme.

## Running tests

```powershell
pip install -e ".[dev]"
pytest
```

Tests run against an isolated SQLite database (no Postgres required). Inside the
running stack you can also run `docker compose exec api python -m pytest`.

## First-run checklist

1. `docker compose up` (or `azd up`).
2. Sign in at http://localhost:5173 with `ADMIN_USERNAME` / `ADMIN_PASSWORD`
   (seeded automatically on first start).
3. **Settings** → enter Tenant ID, Client ID, Client Secret, confirm the Copilot
   SKU id(s), set the backfill window and (optionally) schedule + report-access group.
4. **Test connection** → **Run ingest now** (or start **Backfill**) → watch progress.
5. Explore the dashboard.

The Graph app registration needs application permissions
`AiEnterpriseInteraction.Read.All` and `Directory.Read.All` (admin-consented).

## Deploy to Azure (azd)

Prefer building from source? Infrastructure (Container Apps Environment, api + worker container apps,
PostgreSQL Flexible Server, Container Registry, Log Analytics) is defined in `/infra` and
`azure.yaml`.

```powershell
# Provide the secrets azd will pass to Bicep
azd env set POSTGRES_ADMIN_PASSWORD "<strong-password>"
azd env set FERNET_KEY "<fernet-key>"
azd env set SECRET_KEY "<random-secret>"
azd env set ADMIN_PASSWORD "<admin-password>"

azd up      # provision + build + deploy
azd down    # tear everything down
```

The API container serves the built React bundle, so the deployed app is a single
public endpoint. Swap `DATABASE_URL` to any Postgres to move the database.

> `FERNET_KEY` may be any non-empty string — a proper Fernet key is used as-is, anything else is
> hashed into a valid key. This is what lets the one-click template auto-generate it.

## Build phases

This project is built incrementally (see `COPILOT-BUILD-PLAN.md`):

- **Phase 0** — Scaffold & docker-compose ✅
- **Phase 1** — Database schema & models ✅
- **Phase 2** — Graph client & transforms ✅
- **Phase 3** — Ingestion engine + scheduler ✅
- **Phase 4** — Smart backfill ✅
- **Phase 5** — Metrics API ✅
- **Phase 6** — Auth & secure admin ✅
- **Phase 7** — React dashboard ✅
- **Phase 8** — Deploy (azd + Bicep) ✅
- **Phase 9** — Slicers, sortable tables, product logos, executive briefing ✅
- **Phase 10** — One-click "Deploy to Azure" (ARM + GHCR images) ✅
