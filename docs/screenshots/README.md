# Screenshots

All screenshots in this folder are captured from a throwaway local instance
running seeded demo data. **Never capture them from a deployment connected to a
real tenant** — every name, department and prompt count would be real.

## Producing them

1. Bring the stack up somewhere with Docker Compose, using a copy of the repo
   and its own database:

       cp .env.example .env
       # set FERNET_KEY (see the comment in .env) and pick free ports
       docker compose up -d --build

2. Sign in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`. Leave the
   Entra fields in Settings **empty** — with no tenant credentials configured the
   app cannot make a Graph call, which is what keeps a screenshot run safely
   away from live data.

3. Settings → Demo data → **Load demo data**, then sign out and in again. The
   sign-in picks up the demo persona, which is what makes the personal pages
   ("Your Copilot usage") show anything.

4. Capture at a **1680 × 1050** viewport so the sidebar and the widest tables fit
   without horizontal scrolling. Existing files use that size; matching it keeps
   the README images consistent.

5. Use the theme toggle in the sidebar for the `-dark` variants.

## Naming

`<page>.png`, with `<page>-dark.png` for the dark-mode pair where one exists.
Every file here should be referenced from `README.md`; an unreferenced
screenshot is either a missing section or a leftover to delete.

## Current set

| File | Page |
|---|---|
| `overview.png` / `overview-dark.png` | Overview |
| `briefing.png` | Executive briefing |
| `usage.png` | Usage |
| `leaderboards.png` | Leaderboards |
| `tenant-users.png` | Tenant users |
| `personal.png` / `personal-dark.png` | Your Copilot usage |
| `settings.png` | Settings |
