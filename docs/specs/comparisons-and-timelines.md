# Spec — peer comparisons, timelines and scan history

Status: approved 2026-09-30 · Applies to all four solutions
(M365 Copilot Usage Reporter, M365 Copilot Cowork Reporter,
M365 Copilot Prompt Analyser, Copilot Studio Agent Quality Reporter).

Follows [`suite-consistency-pass.md`](suite-consistency-pass.md). This copy lives
in Usage Reporter, which carries the shared foundation; the same file is
committed to the other three.

---

## Problem

Seven things, reported after living with the suite for a day.

1. **A real app is shown by its internal name.** Usage Reporter lists
   `CoworkChat` in the app breakdown, with no logo. It is Copilot Cowork, and
   it should say so.
2. **Only one solution compares you with anyone.** Prompt Analyser has a "GCSE
   vs team" chart and the others have nothing — so "am I using this well?" is
   answerable in one app out of four.
3. **And that one comparison is mislabelled.** Prompt Analyser's chart draws a
   bar named *Team average* from `avg(gcse_lever)` with **no filter at all** —
   it is the average across the entire tenant. In a large tenant that is a
   materially different number from the one the label promises.
4. **Agent Quality cannot join its data to people.** It knows a creator's UPN
   and nothing else — no department, no manager — because its worker only talks
   to Dataverse and App Insights.
5. **The same page is called two different things.** *Historical backfill* in
   Prompt Analyser, *Backfill* in Usage Reporter.
6. **Only Agent Quality records what it did.** The other three write `job_runs`
   rows on every collection and then never show them, so "did last night's pull
   work?" has no answer in the UI.
7. **Personal pages show totals but not shape.** You can see how many prompts
   you sent; you cannot see whether you sent them steadily or all in one week.
   Usage Reporter's page is also the only one with a product name in its title
   ("Your Copilot usage" against "Your coaching", "Your activity", "Your
   agents").

## Non-goals

- No change to how any figure is calculated, beyond the team comparison being
  filtered to an actual team.
- No full tenant directory sync in Agent Quality. Only the people who appear as
  agent creators are looked up.
- Desktop only, as before.
- No new charting library. Everything uses the suite's existing recharts
  components and palette.

---

## Decisions taken

| Question | Decision |
|---|---|
| Comparison shape | **You / your team / your organisation**, three real series, everywhere |
| Prompt Analyser's mislabelled chart | **Corrected**, not copied |
| What "team" means | **Department**, falling back to people sharing your manager; omitted entirely when neither is known |
| Agent Quality directory data | **Entra lookup of identified creators only** — not the whole tenant |
| Backfill menu label | **Historical backfill** in all four |
| Run-history page name | **Scan history** in all four, under `ADMINISTRATION` |
| Agent Quality's score timeline | **Average score over time with a best-to-worst band**, plus biggest movers |
| Personal timelines | **Daily bars with a rolling-average trend line** |

---

## Definitions

Pinned here because each was left open on the first draft, and four
implementations of an open question are four different answers.

**Comparison period.** All three series use the **same window as the rest of
the personal page** — the period the page's filters resolve to, defaulting to
the last 30 days. Comparing your 30 days against a team's all-time total would
flatter the team by however long it has existed.

**Percentile population.** Your percentile is stated **against the
organisation**, not against your team, and the panel says so. A team of four
makes team-relative percentiles meaningless — you are in the top 25% by
arithmetic rather than by doing anything.

**Minimum team size.** A team series is only drawn when the grouping contains
**at least five people other than the viewer**. Below that it is omitted,
exactly as an unknown team is.

This is not a presentation preference, it is a disclosure rule. "Aggregates
only" stops being true at small n: in a team of two, the team average and your
own figure together give the other person's exact number, and anyone can do
that arithmetic in their head. The threshold applies to whichever grouping is
in use, department or manager — falling back from a department of one to a
manager group of two fixes nothing.

A consequence worth stating plainly: in a small tenant, or a tenant that
populates departments sparsely, most people will see two series rather than
three. That is the correct outcome. The alternative is a report that quietly
discloses individuals' usage to their colleagues.

**Job kinds.** `job_runs.job_name` is not a tidy enum, and — this is the part
easy to get wrong — **the set differs per repo**. Usage Reporter writes `daily`,
`manual`, `users` and `backfill`, with `scheduled` also present in production
rows. Cowork Reporter writes `scheduled`, `manual`, `backfill` and two of its
own, `csv-cowork-usage` and `csv-credit-consumption`, and never writes `daily`
or `users` at all.

So the mapping is a **per-repo superset**, not a shared constant: each app
enumerates what it actually writes — check the code, do not assume — and also
carries the siblings' values, so a row written under another schema still
reads. And an unmapped kind must render as its **raw value** rather than
vanishing, because a run that happened and is not listed is worse than one
labelled awkwardly. That fallback is what makes getting the list slightly wrong
survivable.

**Run statuses.** Six values exist across the four codebases: `running`,
`preparing`, `success`, `completed`, `failed`, `cancelled`. They map to three
indicators:

| Indicator | Statuses | Word |
|---|---|---|
| `●` | `success`, `completed` | Succeeded |
| `◐` | `running`, `preparing` | In progress |
| `○` | `failed`, `cancelled` | Failed / Cancelled |

`success` and `completed` mean the same thing and differ only by which module
wrote the row. Normalising the vocabulary at the source is out of scope here;
the display layer absorbs it, and this table is the single place that mapping
is decided.

---

## Flows

### Seeing how you compare

On each solution's personal page, a **How you compare** panel shows three bars
per measure: you, your team, your organisation, with your percentile.

"Your team" is your department. Where a tenant does not populate departments,
it falls back to the people who share your manager. **When neither is known the
team series is left out** rather than drawn at zero — an empty bar reads as
"you are miles ahead of your team" when it actually means "we do not know who
your team is".

Measures per solution:

- **Usage Reporter** — prompts, conversations, apps used. Note `by_user`
  currently returns a prompt count only, so distinct-apps-per-person is new
  aggregation rather than a column that already exists.
- **Prompt Analyser** — the GCSE levers (the existing chart, correctly filtered)
- **Cowork Reporter** — sessions, tools per session *(already built)*
- **Agent Quality** — agents created, average score

### Agent Quality learning who its creators are

Agents carry a creator UPN from Dataverse. A new sync step looks **those UPNs
up** in Microsoft Graph — not the tenant — and stores display name, department,
manager and office against them. That is what makes the team comparison
possible there, and it turns the Agent creators listing into something with
real names and departments rather than bare sign-in addresses.

Needs `User.Read.All` on that app registration, which is a consent step. A
creator who cannot be resolved (left the company, a service principal) is kept
and shown by UPN — dropping them would silently lose their agents.

Because the lookup is scoped to creators, **a viewer who has never created an
agent has no directory row and therefore no team**. They see their own figures
and the organisation's, and no team series — the same two-series outcome as an
unknown team, reached for a different reason. Widening the sync to resolve
viewers as well would mean enumerating people who have nothing to do with the
data, which is the tenant-wide sync this was deliberately scoped away from.

### Checking a collection actually ran

**Scan history**, under `ADMINISTRATION` in all four: every run with what kind
it was, when it started, how long it took, what it wrote, and whether it
succeeded — using the kind and status vocabulary pinned in Definitions above,
which is wider than it looks. Failures show their error. This is what
`job_runs` has always recorded and nothing ever displayed.

Agent Quality keeps its own scan runs here, which is the page's original
meaning in that app.

### Seeing the shape of your usage

Personal pages gain a timeline: daily bars with a rolling-average line over
them, matching the treatment the Usage page already uses for per-app trends.

- **Usage Reporter** — prompts and conversations per day
- **Prompt Analyser** — prompts per day
- **Cowork Reporter** — sessions per day *(already built; gains the trend line)*
- **Agent Quality** — your agents' average score per scan

### Agent Quality's history becoming a timeline

The History page becomes average score over time across whatever the filters
select, with a shaded best-to-worst band behind the line so spread is visible
alongside direction, and a list of the biggest movers since the previous scan.
Filterable by **environment**, **creator** and **agent**.

---

## Acceptance criteria

**Naming and labels**
- `CoworkChat` displays as **Cowork** with the Cowork logo, in every app that
  shows app names. Historical rows already stored as `CoworkChat` display
  correctly — the mapping is at display time, not only at ingest.
- Usage Reporter's personal page is titled **Your usage**.
- The backfill menu item reads **Historical backfill** in all four.
- The run-history page is **Scan history**, under `ADMINISTRATION`, in all four.

**Comparison**
- Three series render where team is known; two where it is not, with no empty
  bar and no zero.
- Prompt Analyser's chart compares against the caller's actual team; its
  organisation series is labelled as the organisation.
- A person whose team has fewer than five other people in it sees two series,
  not three — the team row is omitted rather than drawn from a group small
  enough to identify someone.
- A person in a department of one is a case of the above, and sees no error.
- The comparison never exposes another individual's figures — aggregates only,
  as the existing personal-view rule requires.
- All three series cover the same period, and the panel names the period.
- The percentile states the population it is measured against.

**Agent Quality directory**
- Creators resolve to display name, department and manager.
- An unresolvable creator still appears, keyed by UPN.
- The sync looks up only UPNs present on agents; it never enumerates the
  directory.

**Scan history**
- Shows scheduled, manual and backfill runs, newest first, with status as
  shape-plus-word (● ◐ ○), never colour alone.
- A failed run shows its error.
- Every `job_name` the code can write is listed, including `users` and
  `scheduled`; an unrecognised kind renders as its raw value rather than
  being filtered out.
- Both `success` and `completed` render as Succeeded, not as two states.
- Empty state explains that nothing has run yet and how to start one.

**Timelines**
- Daily bars plus a rolling-average line, on the suite palette.
- A day with no activity renders as an empty slot, not a gap in the axis.
- Agent Quality's score timeline responds to all three filters.

---

## Verification

`pytest` per repo · `tsc --noEmit` and the frontend build · the new CI gate ·
migrations exercised against real Postgres · every changed screen screenshotted
light and dark from a locally seeded instance with **no tenant credentials
configured**, so no Graph call is possible and no deployed instance or tenant
is touched.
