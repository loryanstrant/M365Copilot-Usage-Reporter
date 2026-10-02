# Spec — customer branding

Status: approved 2026-10-02 · Applies to all four solutions
(M365 Copilot Usage Reporter, M365 Copilot Cowork Reporter,
M365 Copilot Prompt Analyser, Copilot Studio Agent Quality Reporter).

This copy lives in Usage Reporter, which carries the shared foundation. The
same file is committed to the other three repos.

---

## Problem

Every install of every solution looks identical, and looks like the author's.
A customer who deploys one into their own tenant and puts it in front of their
own staff has no way to make it read as their organisation's tool.

1. **There is nowhere to put a customer's logo.** The product marks
   (`frontend/public/app-logo.png`, the Copilot Studio SVG) are hard-coded into
   `Layout.tsx` and `LoginPage.tsx`. A customer cannot add theirs beside them.
2. **The accent colour is a compile-time constant.** `brand-50…950` lives in
   `frontend/tailwind.config.js` and is baked into ~111 class names across 19
   files by Tailwind at build time. Changing it means rebuilding the image,
   which a self-hosting customer running a published GHCR tag cannot do.
3. **A naive colour swap would break readability in dark mode.** Call sites
   already reach for *different* stops per mode (`text-brand-600
   dark:text-brand-500`), so one colour cannot simply be substituted — light
   and dark need separate, separately-checked ramps.
4. **A naive colour swap would also break the charts.** `CHART_COLORS`
   (`frontend/src/components/chartTheme.tsx`) and the pass/fail/severity/grade
   palettes carry *meaning*. Repainting them from an arbitrary brand colour
   makes two series indistinguishable and defeats the status conventions.
5. **There is no writable volume to upload into.** `docker-compose.yml` mounts
   only `pgdata` and the SPA bundle is baked into the image, so an uploaded
   logo written to `frontend/dist` would work in development and vanish on the
   next release.

## Non-goals

- **No mobile or narrow-width work**, consistent with
  `suite-consistency-pass.md`. These are desktop dashboards. The branding
  surfaces must not *worsen* narrow-width behaviour, and are checked at 380px,
  but no drawer or responsive sidebar is introduced.
- **Chart colours are never branded.** `CHART_COLORS`, `SvgDefs.tsx` gradient
  stops, and every pass/fail/severity/grade colour stay exactly as they are.
- **Status never becomes colour-only.** Branding adds no colour-coded state.
  Existing shape+word conventions (`●`/`◐`/`○`, `✓`/`○`) are reused.
- **The browser-tab favicon stays the product's.** There is only one favicon
  slot and the product keeps it.
- **No app-wide Content-Security-Policy.** The locked-down CSP applies to the
  logo response only. An app-wide policy is separate, larger work — the SPA
  uses inline styles and Vite module scripts — and would break `npm run dev`.
- **No cross-app branding reuse.** Each solution has its own database and is
  branded independently in its own Settings page. No shared config service, no
  copy/paste payload.
- **The unbranded default look does not change, at all.** Including this: the
  product's current `dark:text-brand-500` accent measures **4.00:1** against
  the `slate-900` page background, marginally under WCAG AA's 4.5:1. That is a
  pre-existing condition and fixing it is explicitly *out of scope here*, so
  that this change can be reviewed against identical before/after screenshots.
  A *branded* install gets ≥4.5:1 because its ramp is derived and gated. The
  resulting small inconsistency is intentional; do not "fix" it by brightening
  the default as a side-effect of this feature.
- **No PDF, Excel or print export carries the logo**, because no solution has
  any export surface today beyond Usage Reporter's logo-less CSV.

## Flows

### Setting branding (admin)

1. An admin opens **Settings** and scrolls to **Your organisation's branding**,
   the last card on the page.
2. They optionally type an **Organisation name**.
3. They choose a **Logo** — PNG, JPEG or SVG, up to 1 MB. The file is validated
   in the browser first (type, size, ≤4000px) so the common mistakes cost no
   round trip, then uploaded, sanitised server-side and stored in Postgres.
4. If the logo is dark, the app says so and pre-ticks **Show my logo on a white
   panel in dark mode**. They may instead upload a **Logo for dark
   backgrounds**, which takes precedence over the panel.
5. They pick an **Accent colour**. Two live mocks — one light, one dark — show
   a nav pill, a primary button, a link and an input in the pending colour,
   without disturbing the rest of the page.
6. If the derived dark accent would fall below 4.5:1, the app brightens it and
   says so in words with the resulting ratio.
7. They save. The change takes effect immediately, with no redeploy.
8. **Reset to the product's branding** removes the colour, the name and both
   logos after an in-card confirmation, returning the app to its default look.

### Seeing branding (everyone)

- The customer logo appears in a strip across the **top of the sidebar**, above
  the product mark, with a hairline divider beneath — and on the **sign-in
  brand panel** to the right of the product mark, behind a hairline rule.
- The product's own marks remain in place in both. The customer logo is
  **additional, never a replacement**.
- The accent colour reaches buttons, links, the active nav item, focus rings and
  the sign-in gradient. Nothing else.
- Branding is read from a public endpoint and cached in `localStorage`, so it is
  present on the sign-in screen and on first paint of every later visit.

## Acceptance criteria

### Unchanged by default
1. With no branding set, every screen is **pixel-identical** to the build
   before this change, in light and dark mode.
2. With no branding set, `GET /auth/branding` returns no colour and empty
   ramps, and the app injects no override stylesheet.
3. `frontend/src/index.css`'s `:root` and `.dark` blocks each define all eleven
   `--brand-*` stops, as space-separated sRGB channels, equal to the hexes
   `tailwind.config.js` previously carried. Pinned by test.
4. No `brand` entry in `tailwind.config.js` contains a hex; all eleven use the
   `rgb(var(--brand-NNN) / <alpha-value>)` form. Pinned by test.

### Colour
5. For any seed colour, the derived light accent reaches **≥4.5:1** against
   white and the derived dark accent reaches **≥4.5:1** against `slate-900`.
6. Both derived ramps are **monotonic** — relative luminance strictly decreases
   from stop 50 to stop 950 — so a contrast lift can never invert the ramp.
7. When white text on the sign-in gradient's lightest stop would fall below
   4.5:1, the gradient uses one stop deeper (`800/700/600` rather than
   `700/600/500`).
8. When the dark accent is brightened, the UI says so in a sentence containing
   the resulting ratio.
9. Derivation is deterministic, and achromatic seeds (`#000000`, `#ffffff`,
   `#7f7f7f`) produce a usable grey ramp without error.
10. `CHART_COLORS`, `SvgDefs.tsx` and every status colour are byte-identical
    before and after, with any branding set.

### Logo
11. A PNG, a JPEG and an SVG each upload, store and serve correctly, and the
    served bytes match what was stored.
12. An uploaded SVG is served **sanitised**: a `<script>` or `<foreignObject>`
    is refused outright, and an `onload` attribute is absent from the served
    bytes. A plain exported SVG survives with its geometry intact.
13. A file over 1 MB is refused with `413`; a GIF, and an HTML file renamed
    `.png`, are refused with `400`. Every message is plain English, naming
    neither a MIME type nor a traceback.
14. Logo bytes never appear in any JSON response. The payload carries only
    whether a logo exists and the URL to fetch it from.
15. The logo URL changes when the logo changes, so a replacement is picked up
    immediately; `If-None-Match` returns `304`.
16. A missing logo returns a JSON `404`, never `index.html`.
17. `GET /auth/branding` returns `application/json`, never `index.html` — i.e.
    the branding routes are not shadowed by the SPA catch-all.
18. In dark mode: a supplied dark logo is used; otherwise a logo marked as dark
    renders on a white panel; otherwise the logo renders bare.
19. With no logo but an organisation name set, the name renders as text in both
    logo positions.

### Accessibility and layout
20. Every branding surface is checked by screenshot at desktop width **and
    380px**, in light and dark. The branding card introduces **no horizontal
    scroll** and wraps no worse than the cards beside it.

    Measured, so the bar is honest: at 380px the fixed 240px sidebar leaves
    ~140px of content width, and *every* card on the Settings page — including
    the untouched "Demo data" card, and the page heading — wraps to roughly one
    word per line. That is the pre-existing desktop-only layout this spec's
    non-goals already exclude, not something branding introduced. The test is
    therefore parity with its neighbours, not legibility the rest of the page
    does not have. Making these apps usable at 380px means giving the sidebar
    responsive behaviour, which is a separate piece of work.
21. The logo carries the organisation name as its alt text, or "Customer logo"
    when no name is set.
22. All branding state in the Settings card is conveyed by shape and word, not
    colour alone.

### Hygiene
23. `pytest -q` passes; `npx tsc --noEmit && npm run build` passes.
24. No new Python dependency and no new npm dependency is added.
25. `frontend/src/theme/ThemeContext.tsx` is **not modified** — branding needs
    no JavaScript reaction to a theme change, because the injected stylesheet
    carries both a `:root` and a `.dark` block. A diff touching that file means
    something has gone wrong.
26. `app_config` gains no binary column; logo bytes live in their own table, so
    the hot pre-login config read stays as narrow as it is today.

## Sample brand for testing

`docs/branding-sample/` carries a fictional customer, **Avanoso**, seeded from
Avanade orange `#ff5800` — chosen because a real non-blue brand is the only way
to prove the derivation, and because its light wordmark is dark ink and so
exercises the white-panel fallback. Two files: `avanoso-light.svg` and
`avanoso-dark.svg`.
