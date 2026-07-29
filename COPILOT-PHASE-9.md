# Phase 9 — Report parity + rescued visuals

Goal: close the gap between the running MVP and Loryan's original Power BI report (the "real" pages **and**
the worthwhile TEST-page visuals), and bring back the slicers that went missing. Vocabulary stays
Conversations/Prompts. Ignore data quality (being fixed via deeper backfill) — this is purely
features/visuals/filters.

## How I audited
Compared, side by side:
- Original report = the Avanoso PBIP (all pages, visuals, measures, slicer fields) — fully inventoried.
- Current app = React pages + `api/metrics.py` endpoints + the global FilterBar — read from source and
  confirmed live in the browser (logged in, 1,069 prompts of real data rendering).

---

## GAP 1 — Slicers / filters (biggest regression)
**Original report sliced by:** Date (range **and** relative/GA-relative), App/Feature, **Department**,
**Manager**, **Office Location**, **Company/Entity**, **Job Title**, **User Name**.
**Current app filters by:** Date From/To + App. That's it.

Missing entirely (UI **and** backend):
- Department, Manager, Office Location, Company, Job Title, User Name (search)
- Relative-date presets (Last 7 / 30 / 90 days, etc.)
- Conversation Location (App vs Chat) and Chat Type (Work / Web / Temporary) as filters

Backend blocker: every `metrics.py` function only accepts `date_from/date_to` (and `app` on two of them).
There is **no** dimensional filtering plumbing at all — so this is a backend job first, then UI.

## GAP 2 — Missing pages
| Original page | In app? |
|---|---|
| Laggardboards / Inactive (Top 5 Departments / Locations / Managers + drillthrough) | ❌ none |
| "Where Copilot is used" — Conversation location trends (chat types / Teams / file locations) | ❌ none |
| Prompt (Interaction) Count by Category — grouped column as its own page with slicers | ⚠️ one bar buried in Usage |
| Usage by user (dedicated, with per-user drill) | ⚠️ merged into Usage as a table |

## GAP 3 — Thin pages vs original
- **Leaderboards:** original had **Most active users + Top 5 Locations + Top 5 Departments** (bar charts).
  Current = two plain ranked lists (by prompts / by conversations). Missing all org rollup bars.
- **Overview:** original had an **Interaction Locations** pie (App vs Chat) and licensed/active pies;
  current has only active-vs-inactive. Missing App-vs-Chat and Chat-Type splits, and the **CopilotScore**.

## GAP 4 — Rescued TEST-page visuals never built (promised in Phase 7)
The plan said add **ECharts** for these; the app only uses Recharts and none were built:
- **Streamgraph + stacked area + pie** for chat types / Teams locations / file locations ("Where Copilot is used")
- **Sunburst** (app → chat type, or department → app)
- **Radar** (usage profile across apps by department/user)
- **Small-multiples trend grid** (area + KPI card per app)

## GAP 5 — Measures computed but not surfaced
- **CopilotScore** (DAX ladder) — not exposed by any endpoint.
- **Chat Type** (Work/Web/Temporary) and **Conversation Location** (App/Chat) breakdowns — not surfaced.
- **File / Teams location** breakdowns — not surfaced.
- Manager / Department / Office / Company / Job Title rollups — not surfaced.
- Avg prompts per conversation **per user per app** (combined) — not surfaced.

## (Minor, optional) App-name normalisation
Live app shows raw `ProactiveChat`; original normalises Copilot surfaces. This is a transform tweak in
`worker/transforms.py`, not data quality — cheap to fix while we're in here. Include if desired.

---

# Phase 9 build plan (sub-phases, in order)

Each is independently shippable. Backend first so the UI has data to bind to.

### 9.1 — Backend: dimensional filters + new endpoints
- Add a reusable filter model: `date_from/date_to`, `app`, `department`, `manager_id`, `office_location`,
  `company`, `job_title`, `user_search`, `chat_type`, `conversation_location`. Apply across
  summary/daily/by-app/by-user by joining `prompts` → `entra_users`.
- New endpoints:
  - `GET /metrics/filters` — distinct values for every slicer (feeds the UI dropdowns).
  - `GET /metrics/locations` — chat-type / Teams-location / file-location counts **and** daily trend.
  - `GET /metrics/leaderboard-rollups` — top users / departments / offices / managers.
  - `GET /metrics/laggards` — licensed users with no/low usage in window + top laggard dept/office/manager.
  - `GET /metrics/chat-types` and conversation-location split.
  - `GET /metrics/copilot-score` — the SWITCH-ladder score (thresholds configurable).
- Unit tests on a seeded dataset for each.

### 9.2 — Global filter bar expansion
- Extend `FiltersContext` + `FilterBar` with Department, Manager, Office, Company, Job Title, User search,
  and relative-date presets; populate from `/metrics/filters`; make all pages consume them.

### 9.3 — Overview enrichment
- Add Conversation Location (App vs Chat) pie, Chat Type (Work/Web/Temporary) breakdown, and a
  **CopilotScore** KPI card. Keep the existing cards/trend.

### 9.4 — Laggardboards / Inactive page (+ drillthrough)
- Licensed-but-inactive list; Top 5 Departments / Locations / Managers bars; row→user drillthrough.

### 9.5 — Leaderboards parity
- Add Top 5 users / departments / offices / managers bar charts alongside the ranked lists.

### 9.6 — "Where Copilot is used" (Locations) page  ← needs ECharts
- Streamgraph + stacked area + pie for chat types / Teams locations / file locations, over time.

### 9.7 — Prompt Count by Category page
- Promote the 30-day bucket chart to its own page: grouped column + the category slicers.

### 9.8 — Advanced rescued visuals ← ECharts
- Sunburst (app → chat type / dept → app), Radar (app usage profile by dept/user), and the
  small-multiples per-app trend grid.

### 9.9 — (optional) App-name normalisation tidy
- Map remaining Copilot surface names in `worker/transforms.py`; re-run ingest.

---

## Delivery options
- **I build it** (no Copilot credits): I own the repo already; I can do 9.1→9.8 directly, test each, and
  you review in the browser. Recommended given your credit budget.
- **Copilot builds it:** each sub-phase above converts to a paste-ready prompt.

Suggested order to get visible wins fast: 9.1 → 9.2 → 9.3 → 9.6 (locations) → 9.4/9.5 → 9.7 → 9.8.
