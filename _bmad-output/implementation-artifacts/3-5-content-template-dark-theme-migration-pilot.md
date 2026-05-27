# Story 3.5: Content Template Dark-Theme Migration — Pilot (Services List)

Status: Draft

> **Scaffold note (2026-05-26):** Created to set the *pattern* for migrating
> legacy light-themed content templates onto the dark-first design system, per
> AD-7's per-template coexistence rule. Numbered 3.5 as the continuation of the
> Epic 3 Tailwind migration (3.1 pipeline → 3.2 layout shell → 3.5 content).
> Pilot template (`services/list.html`) is **swappable** — see "Why Services
> List" in Dev Notes. Once this pattern is validated, the remaining templates
> become sibling stories (see "Follow-on backlog").

## Story

As a **user (all personas)**,
I want the Services list view to render in the dark-first design system instead of legacy light cards,
So that page content matches the dark shell/sidebar and the UI presents one consistent visual language (no white cards floating on the dark page, no bright-white filter pills).

## Context / Problem

The layout shell, top bar, and sidebar were migrated to Tailwind dark tokens in
Story 3.2 (AD-3), but page **content** inside `{% block content %}` still uses
the legacy `main.css` light theme: `.card { background: white }`,
`.filter-btn { background: #fff }`, dark-on-dark legacy page headings, etc. The
result is a mid-migration mix — a dark shell wrapping white content cards. Per
AD-7, that legacy CSS is left untouched until each template is migrated **as a
whole**. This story migrates the first content template end-to-end to prove the
recipe.

## Acceptance Criteria

### AC1: Page surfaces use dark elevation tokens
**Given** the Services list page (`services/list.html` + `services/_list_content.html` + `services/_health_feed_items.html`)
**When** it is migrated to Tailwind
**Then** the page background is `surface-base` (#0f0f1a), service cards are `surface-raised` (#1a1a2e), and any overlay/expanded panel is `surface-overlay` (#252540)
**And** depth is communicated through shade (Ground → Raised → Floating), not box-shadow or border (per UX spec elevation system)

### AC2: Text uses the token hierarchy
**Given** the migrated page
**When** text renders
**Then** headings/primary content use `text-primary` (#f8fafc), labels/metadata use `text-secondary` (#94a3b8), and placeholder/tertiary text uses `text-muted` (#64748b)
**And** the page heading is legible on the dark background (no dark-on-dark legacy heading color)

### AC3: Filter pills + buttons use design tokens
**Given** the status/sort filter pills (`filter-btn`, `filter-btn-healthy/warning/critical`) and any action buttons
**When** migrated
**Then** inactive pills use a transparent/`surface-raised` background with a `surface-overlay` border and `text-secondary` label; the active pill uses `primary` (#6366f1)
**And** status filters use their status token for the active/accent state (healthy=green #22c55e, warning=amber #f59e0b, critical=red #ef4444)
**And** no pill renders as bright white on the dark background

### AC4: Status semantics preserved
**Given** service health status indicators (left borders, chips)
**When** migrated
**Then** color continues to mean status only: green healthy / amber warning / red critical / gray muted-or-completed (no decorative color), per the UX spec color-usage principles

### AC5: Focus + motion accessibility carried forward
**Given** interactive elements (pills, links, buttons)
**When** focused via keyboard
**Then** they show the standard focus-visible ring (`ring-2 ring-primary ring-offset-2 ring-offset-surface-base`)
**And** any transition respects `prefers-reduced-motion` (`motion-reduce:transition-none`)

### AC6: Clean migration — no legacy leakage, no half-Tailwind
**Given** AD-7's coexistence contract
**When** the template is migrated
**Then** ALL styling for the migrated template's elements is Tailwind utilities — no element keeps a legacy `main.css` class (`.card`, `.filter-btn`, etc.) and Tailwind utilities on the same element ("never mix on same element"; "no half-Tailwind templates")
**And** the full set of relevant properties is set via utilities so legacy bare-element selectors (`main`, `nav`, `h2`, …) cannot leak through on uncovered axes (AD-7 implication)
**And** legacy CSS rules that become unused *only* by this template are NOT deleted yet (other unmigrated templates may still use `.card`/`.filter-btn`); a global removal is a separate cleanup once all consumers migrate

### AC7: Tests stay green and prove the migration
**Given** the project test convention (render assertions + static-source assertions; no JS runner)
**When** the migration lands
**Then** existing tests pass (`cd ui && ./.venv/bin/pytest -q`)
**And** a render test asserts the migrated template emits the dark token utility classes (e.g. `bg-surface-raised`, `text-text-secondary`, `bg-primary`) and no longer emits the legacy classes it replaced
**And** `make tailwind-build` succeeds and the new utility strings appear in the compiled (gitignored) `tailwind.css`

## Tasks / Subtasks

- [ ] Task 1: Inventory the template's surfaces (AC: #1–#4)
  - [ ] 1.1: List every element in `services/list.html`, `_list_content.html`, `_health_feed_items.html` and its current legacy class + computed light color
  - [ ] 1.2: Map each to a target token (card→`bg-surface-raised`, heading→`text-text-primary`, label→`text-text-secondary`, pill active→`bg-primary`, status→status tokens)
- [ ] Task 2: Migrate the container + cards to tokens (AC: #1, #2, #6)
  - [ ] 2.1: Replace `.card` usages with `bg-surface-raised rounded-lg p-5` (+ token text); remove the legacy class from those elements
  - [ ] 2.2: Set full property sets (padding both axes, display) so legacy bare-element rules can't leak (AD-7)
  - [ ] 2.3: Convert headings/labels/empty-state text to the token hierarchy
- [ ] Task 3: Migrate filter pills + buttons (AC: #3, #4, #5)
  - [ ] 3.1: Rebuild `filter-btn` pills as Tailwind (inactive: `bg-surface-raised border border-surface-overlay text-text-secondary`; active: `bg-primary text-white`)
  - [ ] 3.2: Status variants use status tokens for active/accent
  - [ ] 3.3: Add focus-visible ring + `motion-reduce:transition-none`
- [ ] Task 4: Verify in browser (AC: #1–#5)
  - [ ] 4.1: `make tailwind-build`; load `/services/` in preview; inspect computed colors (`preview_inspect`) for card bg = rgb(26,26,46), active pill = rgb(99,102,241), heading legible
  - [ ] 4.2: Tab through interactive elements; confirm focus rings; confirm no bright-white pills
- [ ] Task 5: Tests (AC: #7)
  - [ ] 5.1: Render test: migrated template emits `bg-surface-raised`/`text-text-*`/`bg-primary`; asserts legacy `.card`/`.filter-btn` no longer present on migrated elements
  - [ ] 5.2: `cd ui && ./.venv/bin/pytest -q` green
- [ ] Task 6: Document the recipe (AC: all)
  - [ ] 6.1: Capture the token-mapping recipe + gotchas in this story's Dev Notes so follow-on template stories copy it

## Dev Notes

### Why Services List as the pilot
- **Bounded:** one route, three templates, no SSE/streaming/collaboration complexity (unlike investigation detail).
- **Representative:** exercises every token category — `surface-raised` cards, `text-*` hierarchy, `filter-btn` pills, status colors, empty-state text, focus rings.
- **Motivated:** directly fixes the bright-white-filter-pills-on-dark clash observed 2026-05-26 (the pills float on the dark page background above the cards).
- **Swappable:** if you'd rather pilot the highest-value surface, **investigation detail** (`investigations/detail.html`) is the primary product surface per the UX spec, but it's larger/riskier and better done *after* the pattern is proven here.

### Architecture Compliance (AD-3, AD-7) — the per-template contract
- **Dark-first, single palette** (UX spec, Color System): dark is the only palette; color means status; depth via shade not shadow.
- **Coexistence (AD-7):** new components in Tailwind, legacy `main.css` untouched until a template migrates **whole**. "No half-Tailwind templates." "Never mix [Tailwind + legacy] on the same element."
- **Cascade gotchas (AD-7 addendum):** Tailwind utilities are imported **unlayered** so they win class-vs-element specificity (0,1,0 > 0,0,1) but **tie** with legacy class selectors (0,1,0) — and `tailwind.css` loads before `main.css`, so for a tie **legacy wins**. ⇒ When migrating, you must **remove the legacy class from the element** (don't leave `.card` on a `bg-surface-raised` element hoping the utility wins — it won't). Higher-specificity legacy descendant selectors (`.entry-card .header h2`) also win, so migrate the whole subtree.
- **Set full property sets:** legacy bare-element rules (`main { padding }`, `nav { display:flex }`, `h2 { … }`) leak on any axis a utility doesn't cover — set both axes explicitly (the Story 3.2 shell did this with defensive overrides).

### Design Tokens (already in `ui/beeper_ui/static/css/input.css` `@theme`, emitted as `--color-*` :root vars in `tailwind.css`)

| Legacy (light) | Token utility | Hex |
|---|---|---|
| `.card { background:white }` | `bg-surface-raised` | #1a1a2e |
| page bg | `bg-surface-base` | #0f0f1a |
| overlay/expanded | `bg-surface-overlay` | #252540 |
| dark heading text | `text-text-primary` | #f8fafc |
| label/meta text | `text-text-secondary` | #94a3b8 |
| placeholder text | `text-text-muted` | #64748b |
| `.filter-btn.active` (blue) | `bg-primary` | #6366f1 |
| healthy / warning / critical / muted | `*-status-healthy/-warning/-critical/-muted` | #22c55e / #f59e0b / #ef4444 / #6b7280 |

### Button-chrome prerequisite (already landed 2026-05-26 — do NOT redo)
A global button reset now lives in `input.css`:
`button { -webkit-appearance:none; appearance:none; background-color:transparent; border:0 solid }`.
This kills the UA grey chrome (native `appearance:auto` paint + `buttonface` bg +
`outset` border) on ALL buttons — required because Preflight is disabled. Migrated
buttons set their own token bg/border via utilities (specificity wins). Gotcha:
`.btn` is defined **twice** in `main.css` (lines 1531 & 2744). Not relevant once a
button is fully Tailwind, but relevant if you touch legacy `.btn` rules.

### Testing Requirements (project convention — see memory: beeper-ui-clientside-test-convention)
- No JS test runner. Prove client-side via **(1) render assertions** (`client.get(...)` / `app.jinja_env.get_template(...).render(...)` then assert on emitted utility-class strings + aria/data attrs) and **(2) static-source assertions** (read shipped `.css`/`.js`).
- Browser/runtime behavior (computed colors, focus rings) = manual preview verification (AD-8). `make tailwind-build` first (standalone binary; output is gitignored). Flask dev server runs `--no-reload`, so **restart** (not reload) to see template edits.

### Follow-on backlog (sibling stories, same recipe)
After this pilot validates the recipe, migrate the remaining legacy content templates per-template (rough order by value/traffic): `investigations/detail.html` (primary surface) → `investigations/list.html` → `knowledge/*` (entry, index, edit, history, …) → `trust/*` → `health/status.html`, `sources/list.html`, `slo/*`, `spending/*`, `notifications/config.html`, `reports/*`, `analytics/*`, `metrics/*`, `topology/*`, `handoff/*`. Final cleanup story: once a legacy class (`.card`, `.filter-btn`, …) has zero remaining consumers, delete it from `main.css` and drop the Story 3.2 defensive shell overrides (AD-7 "future cleanup option").

### References
- `docs/specs/ux-design-specification.md` — Color System (surface/elevation tokens, dark-first, color-means-status), Typography tokens
- `docs/specs/architecture.md` — AD-3 (atomic layout shell), AD-7 + addendum (Tailwind/main.css coexistence + cascade contract), "custom CSS until migrated", "migration is per-template, not per-class"
- `_bmad-output/implementation-artifacts/3-2-implement-layout-shell-base-template-migration.md` — layout shell precedent (defensive overrides pattern)
- `ui/beeper_ui/static/css/input.css` — `@theme` tokens + global button reset
- Memory: `beeper-ui-theme-migration-doctrine`, `beeper-ui-tailwind-preview-workflow`, `beeper-ui-clientside-test-convention`

### Key Risks / Open Questions (resolve during implementation; defaults sensible)
- **Q:** Migrate health-feed-item partial in this story or defer? **Default:** include it — it renders inside the same cards; leaving it legacy would violate "no half-Tailwind template."
- **Q:** Keep card box-shadow? **Default:** drop it — UX spec says depth via shade, not shadow, on dark.
- **Risk:** Legacy descendant selectors (`.service-card …`) outranking utilities. **Mitigation:** remove legacy classes from the whole migrated subtree; verify computed colors in preview.

## Dev Agent Record

### Agent Model Used
_(to be filled by implementing agent)_

### Debug Log References
_(none yet)_

### Completion Notes List
_(none yet)_

### File List
_Expected to touch:_
- `ui/beeper_ui/templates/services/list.html`
- `ui/beeper_ui/templates/services/_list_content.html`
- `ui/beeper_ui/templates/services/_health_feed_items.html`
- `ui/tests/` — new render test for the migrated template
- (build) `ui/beeper_ui/static/css/tailwind.css` (gitignored, rebuilt)

### Change Log
| Date | Change | Author |
|---|---|---|
| 2026-05-26 | Story scaffolded (pilot for content dark-theme migration) | Claude |
