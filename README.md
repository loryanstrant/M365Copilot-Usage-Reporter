# M365 Copilot Usage Reporter

Self-hosted adoption reporting for **Microsoft 365 Copilot**. It ingests usage from Microsoft
Graph, stores it in PostgreSQL, and serves a web dashboard showing who is using Copilot, where,
how often, and who holds a licence but isn't getting value from it. A replacement for the
Power Platform + Power BI version — no Power BI licence, no Power Platform, and no data leaves
your subscription. Runs anywhere with `docker compose up`, or deploys to Azure Container Apps
in one click.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Usage-Reporter%2Fmain%2Finfra%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Usage-Reporter%2Fmain%2Finfra%2FcreateUiDefinition.json)

> Community project, MIT-licensed. Not covered by a Microsoft support agreement.

## Screenshots

### Overview

At-a-glance KPIs, usage over time (prompts vs conversations, by month), and the top surfaces.

![Overview](docs/screenshots/overview.png)

### Executive briefing

A plain-English, auto-generated snapshot with period-over-period deltas, highlights, watch-outs, and
suggested actions.

![Executive briefing](docs/screenshots/briefing.png)

### Usage

Per-app monthly trends (with trendlines and product logos), engagement distribution, and sortable
per-app / per-user tables.

![Usage](docs/screenshots/usage.png)

### Leaderboards

Top departments, offices, and managers, plus the most active users by prompts and conversations.

![Leaderboards](docs/screenshots/leaderboards.png)

### Dark mode

Every page supports a light and dark theme.

![Overview in dark mode](docs/screenshots/overview-dark.png)

## Deploy to Azure (one click)

The button provisions everything into a resource group of your choice: a PostgreSQL flexible
server, a Container Apps environment, and the **api** + **worker** container apps (pulled as
prebuilt public images from GitHub Container Registry). You only enter an **admin password** — the
database password and encryption keys are generated for you. When the deployment finishes, open the
`dashboardUrl` output, sign in, and complete the in-app **Settings** to connect Microsoft Graph.

To deploy from source with `azd` instead, see [`docs/deploy.md`](docs/deploy.md).

## After it's deployed

**1. Open the dashboard.** In the portal, go to your resource group → open the deployment (or
Deployments → the `Microsoft.Template` run) → **Outputs** → copy **`dashboardUrl`**. That is your app.
It's served by the **`…-api-…`** Container App (the `…-worker-…` one has no web UI — it just runs
ingestion in the background). You can also get the URL from the api Container App's **Overview →
Application Url**.

**2. Sign in.** Username is what you set as **admin username** (default `admin`); password is the
**admin password** you chose at deploy time.

**3. Connect Microsoft Graph.** Go to **Settings**. The first-run wizard walks you through creating
an Entra **app registration** with the two application permissions
(`AiEnterpriseInteraction.Read.All`, `Directory.Read.All`, admin-consented) and a client secret.
Paste **Tenant ID**, **Client ID**, **Client secret**, then **Test connection**.

**4. Load data.** Select **Run now** for the last 24 hours, or open **Backfill** to pull history
(default 30 days). The **Data status** card on Settings shows Prompts / Conversations / **Licensed
users** / Directory users; the **Backfill** page has a run history table with per-run stats.

Want to look around before connecting a tenant? **Settings → Demo data → Load demo data** fills the
dashboards with plausible fictional data. Clear it again from the same card before your first live
run. Nothing is ever seeded or wiped automatically.

### Enabling Entra ID single sign-on (optional)

By default the dashboard is protected by the single admin password. You can additionally let
colleagues sign in with their **work account** (read-only viewer role) via **Container Apps Easy
Auth** — administration stays behind the password. You can turn this on **at deploy time or later**.

**One-time prerequisite (either path):** an Entra **app registration** for sign-in (you can reuse
the reporter's own). Note its **Application (client) ID**, create a **client secret**, and after
deployment add the redirect URI
`https://<your-dashboardUrl>/.auth/login/aad/callback` under **Authentication → Web**. If you plan to
restrict viewers to a security group, also add a **groups** claim under **Token configuration**.

**Option A — at deploy time (recommended):** on the **Deploy to Azure** form, open the
**Authentication** tab and set **Enable Entra ID single sign-on = Yes**, then paste the app
registration **client ID**, **client secret**, and (optional) **tenant ID**. Everything is wired up
automatically; grab the **`entraRedirectUriToRegister`** deployment output and add it to the app
registration as above.

**Option B — after deployment:** open the **`…-api-…`** Container App → **Settings →
Authentication** → **Add identity provider** → **Microsoft**, use your app registration's client ID
+ secret, and set *unauthenticated requests* to **Allow** (the app still gates admin behind the
password; SSO users become viewers). Add the redirect URI as above.

Either way, once enabled the sign-in page shows a **"Sign in with Microsoft"** button and returning
users are signed in silently. To restrict who may view, set a **report access group** on the
**Settings** page — only members of that Entra group are admitted.

Full details and screenshots: [`docs/deploy.md`](docs/deploy.md#entra-single-sign-on-optional).

### Where to find run history, logs, and errors

- **In the app:** **Settings → Data status** (last run + counts) and **Backfill** (per-run history
  table with prompts/lookback/status). A failed run shows its error message in the run's stats.
- **Container logs (the real detail):** a manual **Run now** and **Backfill** run inside the
  **`…-api-…`** Container App, so their logs live there — open it → **Monitoring → Log stream**
  (live), or **Logs** to query `ContainerAppConsoleLogs_CL`. The scheduled background ingest runs in
  the **`…-worker-…`** Container App — check its log stream for scheduled-run errors.
- **A run that "completes instantly with no data" almost always means zero Copilot-licensed users
  were found** (nothing to query). Check **Settings → Data status → Licensed users**, or the
  **Copilot-licensed users** number shown by **Test connection**. If it's 0, the configured Copilot
  **SKU ID** doesn't match any assigned licences in the tenant — set the correct SKU under Settings →
  *Copilot SKU IDs* (the default is Microsoft 365 Copilot, `639dec6b-bb19-468b-871c-c5c441c4b0cb`).

## What it does

- **Overview** — KPI cards (Prompts, Conversations, avg prompts/conversation, adoption) plus trend,
  active-vs-inactive, and usage-by-app charts.
- **Executive briefing** — an auto-generated, plain-English summary with period-over-period deltas.
- **Usage** — per-app and per-user tables (CSV export), engagement buckets, and a department
  usage profile.
- **Where it's used** — the surfaces and locations Copilot is being invoked from.
- **Leaderboards** — top departments, offices, managers and users.
- **Laggards** — licensed users with no activity in the window: who to coach first.
- **Coaching pairs** — matches low-usage users with a high-usage peer in the same team.
- **Licences** — enabled, allocated and available over time.
- **Settings (admin)** — Graph config (secret write-only, Fernet-encrypted), a guided
  app-registration wizard, test connection, run now, demo data, and a resumable **backfill** with
  live progress.
- **Entra single sign-on (optional)** — colleagues view the report with their work account
  (read-only), optionally gated to an Entra security group.
- Global date-range and app **filters**, **CSV export**, and a **light/dark** theme throughout.

## Prerequisites & permissions

- A **Global Administrator** (or Privileged Role Administrator plus Application Administrator) to
  create the app registration and grant admin consent.
- Microsoft 365 Copilot licences assigned in the tenant.
- PowerShell 7 with the Microsoft Graph SDK, if you'd rather script the registration.

The app registration needs these **application** permissions (not delegated), both admin-consented:

| Permission | Why |
| --- | --- |
| `AiEnterpriseInteraction.Read.All` | Reads Copilot enterprise interaction history — the usage signal itself. |
| `Directory.Read.All` | Resolves users, departments and licences so usage can be grouped and filtered. |

The in-app **Setup guide** page and the Settings wizard both carry a one-shot PowerShell script that
creates the registration, grants consent and prints the three values you need:

```powershell
# Run in PowerShell 7 with the Microsoft Graph SDK.
# Requires a Global Administrator (or Privileged Role + Application admin).
Install-Module Microsoft.Graph -Scope CurrentUser -Force  # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
$needed  = "AiEnterpriseInteraction.Read.All","Directory.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "M365 Copilot Usage Reporter" -RequiredResourceAccess @{
  ResourceAppId  = "00000003-0000-0000-c000-000000000000"
  ResourceAccess = @($roles | ForEach-Object { @{ Id = $_.Id; Type = "Role" } })
}
$sp = New-MgServicePrincipal -AppId $app.AppId

# Grant admin consent for both application permissions
foreach ($r in $roles) {
  New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id `
    -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $r.Id | Out-Null
}

$secret = Add-MgApplicationPassword -ApplicationId $app.Id `
  -PasswordCredential @{ DisplayName = "reporter"; EndDateTime = (Get-Date).AddYears(1) }

Write-Host "Tenant ID:     $((Get-MgContext).TenantId)"
Write-Host "Client ID:     $($app.AppId)"
Write-Host "Client secret: $($secret.SecretText)"
```

## Quick start (local)

```powershell
# 1. Create your env file and a Fernet key
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the printed value into FERNET_KEY in .env

# 2. Start the production stack (api + worker + postgres)
docker compose up -d
```

- **Dashboard + API:** http://localhost:8000
- **API + Swagger docs:** http://localhost:8000/docs
- **API health check:** http://localhost:8000/health
- **Postgres:** localhost:5432 (user/pass/db all `copilot` by default)

This is the production stack: it runs prebuilt images with no bind mounts and no
auto-reload, and the API serves the built dashboard itself — so there is no separate
frontend container or web port. `docker compose up` pulls the published images; add
`--build` to build them locally instead.

Every solution in the suite owns a distinct port block, so all four can run side by
side without clashing:

| Solution | API / dashboard | Postgres |
|---|---|---|
| **M365 Copilot Usage Reporter** | **8000** | **5432** |
| M365 Copilot Cowork Reporter | 8001 | 5433 |
| Copilot Studio Agent Quality Reporter | 8002 | 5434 |
| M365 Copilot Prompt Analyser | 8003 | 5435 |

Override `API_PORT` / `DB_PORT` in `.env` to move them. Only the host side changes —
container-internal wiring is unaffected.

### Developing against it

For hot-reload while working on the code, layer the dev override on top. It builds
locally, bind-mounts the source, enables `uvicorn --reload` and runs the Vite dev
server:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev dashboard is then on http://localhost:5173 (`WEB_PORT`), with the API still
on 8000.

On first start an admin login is seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`
(defaults `admin` / `change-me` — change these).

## First-run checklist

1. `docker compose up` (or deploy to Azure).
2. Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (seeded automatically on first start).
3. **Settings** → follow the guided wizard to create the app registration, then enter Tenant ID,
   Client ID and Client secret, confirm the Copilot SKU id(s), and set the backfill window and
   (optionally) a schedule and report-access group.
4. **Test connection** → **Run now** (or start **Backfill**) → watch progress.
5. Explore the dashboard.

Just evaluating? Skip steps 3–4 and use **Settings → Demo data → Load demo data** instead.

## Data & privacy notes

- **Prompt text is never stored.** The reporter keeps interaction metadata only — who, when, which
  app, which conversation — never the content of what anyone typed or what Copilot replied.
- All data stays in **your** subscription. Nothing is sent to any third-party service.
- The Graph **client secret** is encrypted at rest with a Fernet key and is write-only in the API:
  it can be set and replaced, never read back.
- Sign-in is gated by an admin password; optional Entra SSO grants read-only viewer access and can
  be restricted to a named security group.
- Demo data is clearly labelled as such in Settings, and is only ever created or removed by an
  explicit action.

## License

MIT. Community project — no Microsoft support agreement or SLA.
