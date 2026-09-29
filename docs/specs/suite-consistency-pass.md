# Spec — Copilot reporting suite consistency pass

Status: approved 2026-09-29 · Applies to all four solutions
(M365 Copilot Usage Reporter, M365 Copilot Cowork Reporter,
M365 Copilot Prompt Analyser, Copilot Studio Agent Quality Reporter).

This copy lives in Usage Reporter, which carries the shared foundation. The
same file is committed to the other three repos.

---

## Problem

The four solutions share one architecture but were evolved separately, so the
same idea is implemented three or four different ways and several capabilities
exist in only one of them.

1. **Admin access is a single shared username and password.** An Entra SSO user
   is hard-coded to `viewer` at the OIDC callback (`api/routers/auth.py:141`),
   so the only route to admin is one set of credentials passed between people.
   There is no way to grant admin to a few named users.
2. **The signed-in user is shown as a raw UPN** in the sidebar footer, never as
   a name — even though the ID token already carries the display name and the
   code discards it (`api/oidc.py:51`).
3. **Licence detection finds only one Copilot SKU.** M365 E7 bundles Copilot and
   is invisible; so is a second M365 Copilot SKU (`a809996b-…`) nobody noticed.
   Holders of a bundle with Copilot switched off are counted as licensed.
4. **The four look like four products.** Cowork uses a bespoke card component
   whose cards are invisible in dark mode; there are three different
   `DataTable`s and five chart palettes; KPI tiles have an optional subtitle so
   grid rows go ragged; nav section headings differ, and Agent Quality has three
   unlabelled orphan nav items.
5. **Capabilities are stranded in one app each** — the executive briefing exists
   only in Usage Reporter, the tenant-users listing only in Cowork.
6. **Screenshots and feature listings in all four READMEs are stale.**

## Non-goals

- No mobile or narrow-width work. These are desktop dashboards; each README
  says so.
- No LLM-written briefings. The briefing stays deterministic so it cannot
  invent a number in front of a customer.
- No Entra directory sync for Agent Quality. It gets an "Agent creators"
  listing built from the identity data it already holds.
- The local admin password is **not** removed. It is break-glass, and it is the
  only way to sign in and set the admin group in the first place.
- No test CI is added in this pass (none of the four has any today).

---

## Flows

### Granting admin to a group

1. An existing admin signs in with the local password and opens **Settings**.
2. Beside the existing report-access and organisation-view group fields, they
   paste the object ID of an Entra security group into **Admin group ID**.
3. Anyone in that group who signs in with Entra SSO now has admin. Membership is
   evaluated **per request**, not baked into the token, so removing someone from
   the group takes effect in minutes rather than at their next sign-in — the
   same rationale the existing organisation-view gate is built on.
4. Leaving the field blank means nobody gets admin via SSO. It **fails closed**,
   which is the opposite of the organisation-view gate, where blank means open.

### Seeing who is signed in

The sidebar footer shows the display name, the UPN beneath it in small grey
text, then the role. The local admin account has no directory name, so it falls
back to showing the username alone.

### Counting a Copilot licence

A person is licensed when they hold any SKU containing the service plan
**"Microsoft Copilot with Graph-grounded chat"**
(`M365_COPILOT_BUSINESS_CHAT` / `3f30311c-6b1e-48a4-ab79-725b469da960`) **and**
that plan is not in their `disabledPlans`. The granting SKUs are derived live
from the tenant's own `subscribedSkus`, so E7
(`9a18296a-025f-4e37-9ffa-30bf8d1ce775`), Copilot for Sales, Copilot EDU, both
M365 Copilot SKUs and any future SKU are all covered without configuration.
Settings shows which SKUs matched, read-only, with a manual override behind a
disclosure.

### Evaluating with demo data

Loading demo data binds the local admin to a seeded directory user, so the
personal pages work without Entra. Today they cannot be reached at all without
SSO, which means anyone evaluating the product never sees pages the README
advertises.

---

## Acceptance criteria

**Admin group**
- A member of the configured group signing in via Entra reaches admin-only
  pages and endpoints.
- A non-member signing in via Entra is refused.
- With the field unset, no SSO user gets admin; the local admin still does.
- Removing someone from the group revokes their admin within the group-cache
  window without them signing out.
- Saving Settings resets the group cache, so a changed group ID takes effect
  immediately rather than after five minutes.

**Display name**
- The sidebar shows display name, UPN and role for an SSO user.
- It shows the username alone for the local admin.
- A token issued before this change (no `name` claim) renders without error.

**Licences**
- A user holding E7 with Graph-grounded chat enabled counts as licensed.
- A user holding E7 with that plan in `disabledPlans` does **not**.
- A user holding `a809996b-…` counts, without it being configured anywhere.
- Licence counts aggregate correctly when more than one SKU grants Copilot.

**Consistency**
- One `KpiCard`, `DataTable`, `ChartCard`, `ChartTooltip` and chart palette,
  identical in all four repos.
- Every KPI tile has a subtitle, and the subtitle line is reserved even when
  empty, so no grid row renders ragged.
- Cards are visible in dark mode in all four.
- Nav headings are `YOU` / `ORGANISATION` / `ADMINISTRATION` / `HELP` in all
  four; no nav item sits outside a heading; About sits under `HELP`.
- Status is shown as shape plus word (`●` `◐` `○`), never colour alone.

**Features**
- All four have an executive briefing, reachable directly after Overview.
- Usage, Prompt and Cowork have a Tenant users listing; Agent Quality has an
  Agent creators listing.
- Cowork's Tenant users shows only users who are both licensed and present in
  the report data.
- Cowork's personal page leads with aggregates and charts — KPI row, per-day
  session bars, you-vs-organisation and you-vs-team comparisons, top agents and
  tools — with the session list demoted to a collapsed table.
- Usage Reporter's "Where you use Copilot" is horizontal bars with product
  logos, sortable by usage or by app name.

**Docs**
- Every screenshot in all four READMEs is current, light and dark.
- Feature listings are updated in both places they appear per README — the
  subsections under `## Screenshots` and the prose under `## What it does`
  (`## What it scores` in Agent Quality).
- `docs/screenshots/README.md` records how the screenshots are produced.

---

## Brand

The current Microsoft 365 Copilot mark is
`logos/copilot/microsoft-copilot-510x510.png` in
`loryanstrant/MicrosoftCloudLogos`. Usage and Prompt ship a superseded 2048px
version; Cowork ships a different mark again. Agent Quality uses the Copilot
Studio mark (`logos/copilot-studio/copilotstudio-scalable.svg`), which is
correct for it and only needs refreshing.

All four get the mark at one sidebar treatment
(`h-9 w-9 rounded-lg object-contain`), one login treatment (`h-14 w-14`), and a
real 32px favicon — Usage and Prompt currently serve the full-size 388 KB logo
as their favicon.

---

## Verification

`pytest` per repo (SQLite, no Postgres needed) · `npm run build` per frontend ·
a real click-through of every nav item on a locally seeded instance · and
screenshots of every changed screen, light and dark, checked against
`standards/ux.md`.

Screenshot runs use throwaway local stacks with their own Postgres containers
and **no tenant credentials configured**, so no Graph call is possible and no
deployed instance or tenant is touched.
