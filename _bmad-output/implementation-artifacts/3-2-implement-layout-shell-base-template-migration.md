# Story 3.2: Implement Layout Shell & Base Template Migration

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user (all personas — Diana, Sam, Jordan)**,
I want the UI to have a responsive layout with sidebar and top bar structure,
so that all pages render within a consistent, professional layout shell.

## Background

**Origin:** Epic 3 (UI Layout Shell & Sidebar Navigation), Story 3.2 — the second proper story of the epic, immediately after Story 3.1 installed the Tailwind v4 build pipeline.

**This is the ONE atomic migration step of the entire UI overhaul.** Per AD-3 and the UX specification, the layout shell must be adopted by every route in a *single change* — no feature flag, no gradual rollout. Two navigation systems coexisting (old top-nav + new sidebar) is explicitly called out as the brownfield migration mistake to avoid.

**Current State:**
- `ui/beeper_ui/templates/base.html` is a 51-line template with a fixed-width `<header>` containing a flat top-nav of 15 links (Investigations, Knowledge Base, Sources, Health, Metrics, Spending, Cost Insights, SLO, Services, Topology, Notifications, Handoff, Analytics, Reports, Trust).
- 29 page templates `{% extends "base.html" %}` — they inherit the layout automatically.
- 72 partial templates (prefixed `_`) are `{% include %}`d, do not extend, and need no changes.
- `ui/beeper_ui/templates/components/` exists with only `_command_palette.html` and `_keyboard_help.html`. Story 3.1 did NOT create `layout.html`.
- Tailwind v4 pipeline is live: `tailwind.css` is linked in `base.html` BEFORE `main.css`. Preflight (CSS reset) is **disabled**.
- Test baseline after Story 3.1: **2,032 tests passing, 0 failing.**

**Scope boundary (read carefully):**
- This story builds the layout shell *structure*: the `<aside>` sidebar container, the top bar, and the content area wrapper — all in Tailwind.
- The **sidebar navigation content** (Observe/Learn/Manage groups, nav links, icons) is **Story 3.3** — do NOT build it here. The `<aside>` is a structurally-correct, correctly-sized placeholder this story.
- The **`sidebar_state` block and route-driven auto-collapse / `sessionStorage` JS** is **Story 3.4** — do NOT build it here. This story's sidebar uses pure-CSS viewport-responsive collapse only.

## Acceptance Criteria

1. **Given** the existing `base.html` template
   **When** it is rewritten to include the layout shell
   **Then** it imports the layout macro from `templates/components/layout.html` providing sidebar + top bar + content area structure
   **And** the content area uses `{% block content %}` for page-specific content

2. **Given** the layout shell uses Tailwind classes
   **When** rendered at different viewports
   **Then** layout adapts responsively: sidebar 256px expanded / 64px collapsed, top bar 48px height, content area with 24px padding (FR43)
   **And** no horizontal scrolling occurs between 768px and 1920px+

3. **Given** all 29 page templates extend `base.html`
   **When** the modified `base.html` is deployed
   **Then** every page renders within the new layout shell (AD-3 atomic migration)
   **And** `grep -r "extends" ui/beeper_ui/templates/ --include="*.html"` confirms all templates inherit from `base.html`

4. **Given** the `templates/components/layout.html` macro file is created
   **When** it defines the layout structure
   **Then** it includes top bar with hamburger icon slot, logo, and `{% block breadcrumb %}` slot
   **And** content area wraps `{% block content %}` with proper margin/padding

## Tasks / Subtasks

- [ ] Task 1: Create `ui/beeper_ui/templates/components/layout.html` with the `layout_shell` macro (AC: #1, #4)
  - [ ] 1.1 Define `{% macro layout_shell(breadcrumb='') %}` rendering three regions: `<aside>` sidebar + `<header>` top bar + `<main>` content area
  - [ ] 1.2 Top bar (`<header>`): hamburger icon button (left), "Beeper" logo/wordmark, and a breadcrumb region rendering the `breadcrumb` parameter — height `h-12` (48px)
  - [ ] 1.3 Sidebar (`<aside>`): structural container only, width `w-16 lg:w-64` (64px collapsed below 1200px, 256px expanded at ≥1200px) — leave the interior empty/placeholder; Story 3.3 fills it
  - [ ] 1.4 Content area (`<main>`): wraps `{{ caller() }}` with `p-6` (24px padding); the page is laid out so the sidebar does not overlap content (flex or `ml-*` offset)
  - [ ] 1.5 Use Tailwind utility classes ONLY in this file — design tokens (`bg-surface-*`, `text-text-*`, `border-*`) per the v0.2.0 theme. Never reference `main.css` classes here

- [ ] Task 2: Rewrite `ui/beeper_ui/templates/base.html` to use the layout shell (AC: #1, #2, #4)
  - [ ] 2.1 Add `{% from 'components/layout.html' import layout_shell %}` at the top
  - [ ] 2.2 Remove the old `<header>` top-nav block entirely (the 15 flat nav links)
  - [ ] 2.3 Wrap page content: `{% call layout_shell(breadcrumb=self.breadcrumb()) %}{% block content %}...{% endblock %}{% endcall %}`
  - [ ] 2.4 Define `{% block breadcrumb %}{% endblock %}` (empty default) so child templates can override the top-bar breadcrumb; `self.breadcrumb()` renders it into the macro
  - [ ] 2.5 Preserve everything else verbatim: `{% block title %}`, `tailwind.css`+`main.css` links (in that order), `htmx.min.js`, `{% include 'components/_command_palette.html' %}`, `{% include 'components/_keyboard_help.html' %}`, `command-palette.js`, and `{% block scripts %}`

- [ ] Task 3: Apply responsive Tailwind classes and verify no horizontal overflow (AC: #2)
  - [ ] 3.1 Page background uses `bg-surface-base`; ensure `<body>`/root has no fixed min-width that would force horizontal scroll
  - [ ] 3.2 Verify dimensions resolve to spec: sidebar 64px/256px, top bar 48px, content padding 24px
  - [ ] 3.3 Manually spot-check at 768px, 1200px, and 1920px viewports — confirm zero horizontal scrollbar (manual step; note in completion notes if no browser available)

- [ ] Task 4: Verify atomic migration — all page templates inherit the shell (AC: #3)
  - [ ] 4.1 Run `grep -rh "extends" ui/beeper_ui/templates/ --include="*.html" | sort -u` — every result must be `{% extends "base.html" %}` (currently true: 29 templates, single target)
  - [ ] 4.2 Confirm no template bypasses `base.html` with its own `<html>`/`<head>`

- [ ] Task 5: Update existing tests broken by header removal and add layout shell tests (AC: #1, #2, #3, #4)
  - [ ] 5.1 Search the test suite for assertions on the old top-nav (e.g. `href="/health/"`, `<nav>`, `header-content`, `tagline`) and update/remove them — see Dev Notes "Regression Risk"
  - [ ] 5.2 Add test: rendered base template contains the layout shell regions (sidebar `<aside>`, top bar `<header>`, content `<main>`)
  - [ ] 5.3 Add test: top bar contains the hamburger control and "Beeper" logo
  - [ ] 5.4 Add test: a child template's `{% block breadcrumb %}` override appears in the rendered top bar
  - [ ] 5.5 Add test: sidebar element carries the responsive width classes (`w-16`, `lg:w-64`)
  - [ ] 5.6 Add test: command palette + keyboard help includes still render (regression guard)

- [ ] Task 6: Run full verification (AC: all)
  - [ ] 6.1 Run full suite from `ui/`: `poetry run pytest` — must be ≥ 2,032 passing + new tests, 0 failing
  - [ ] 6.2 Run `poetry run ruff check .` — clean (100-char line length)
  - [ ] 6.3 Generate CSS and spot-check rendering: `make tailwind-build` then load a page

## Dev Notes

### Architecture Reference

- **AD-3 (Layout Shell Template Inheritance Strategy):** Modify `base.html` to include the sidebar + top bar layout shell; all 29 page templates that extend it inherit automatically. Scope: 1 file rewrite (`base.html`) + new `components/layout.html`. The `{% block breadcrumb %}` per-page updates are *incremental* (not required for every page in this story). [Source: _bmad-output/planning-artifacts/architecture.md — AD-3]
- **AD-6 (Sidebar State Management):** Server-rendered default via Jinja2 block + CSS responsive + minimal JS override. **Story 3.4 implements this** — this story only lays pure-CSS responsive groundwork (`w-16 lg:w-64`). [Source: architecture.md — AD-6]
- **AD-7 (Tailwind Pipeline):** Already installed (Story 3.1). `tailwind.css` linked before `main.css`. [Source: 3-1-install-tailwind-css-build-pipeline.md]
- **CSS Coexistence Rule (CRITICAL):** The layout shell is built in **Tailwind ONLY**. Page content inside `{% block content %}` keeps existing custom CSS from `main.css` until individually migrated in later epics. **NEVER mix Tailwind utility classes and `main.css` classes on the same HTML element.** [Source: architecture.md — Frontend Architecture; 3-1 Dev Notes]
- **Atomic migration (non-negotiable):** All routes adopt the shell in one change. No feature flag, no gradual rollout — two navigation systems coexisting is the named anti-pattern. [Source: ux-design-specification.md §"Two navigation systems coexisting"; epics.md Epic 3 / Story 3.2 AC3]

### Canonical File: `components/layout.html`

Per the architecture's canonical component inventory, `components/layout.html` is **Component #1** and defines the "Layout shell (sidebar + top bar + content area)". Use this exact filename. The layout shell is **imported** by `base.html`, NOT extended — `base.html` remains the single template-inheritance root. [Source: architecture.md — "Canonical Component Macro Files"]

`components/sidebar.html` (Component #2, `sidebar_group(...)` macro) is **Story 3.3** — do not create it here.

### Jinja2 Pattern: Macro With Blocks (important — avoids a common mistake)

A Jinja2 `{% macro %}` **cannot contain `{% block %}` tags**. The working pattern that satisfies AC1+AC4:

`components/layout.html`:
```jinja
{% macro layout_shell(breadcrumb='') %}
<div class="flex min-h-screen bg-surface-base text-text-primary">
  <aside class="w-16 lg:w-64 shrink-0 bg-surface-raised border-r border-surface-overlay
                transition-[width] duration-200 ease-in-out">
    {# Story 3.3 fills this with sidebar_group(...) navigation #}
  </aside>
  <div class="flex flex-1 flex-col min-w-0">
    <header class="h-12 flex items-center gap-3 px-4 bg-surface-raised
                   border-b border-surface-overlay">
      <button type="button" aria-label="Toggle sidebar" class="...">{# hamburger #}</button>
      <a href="/" class="font-semibold">Beeper</a>
      <div class="text-text-secondary">{{ breadcrumb }}</div>
    </header>
    <main class="flex-1 p-6 overflow-x-hidden">
      {{ caller() }}
    </main>
  </div>
</div>
{% endmacro %}
```

`base.html` (body):
```jinja
{% from 'components/layout.html' import layout_shell %}
...
{% block breadcrumb %}{% endblock %}
{% call layout_shell(breadcrumb=self.breadcrumb()) %}
  {% block content %}
    {# default welcome content #}
  {% endblock %}
{% endcall %}
```

`self.breadcrumb()` renders the `{% block breadcrumb %}` (defined once in `base.html`, overridable by child templates) and passes its output into the macro as a string. `{% call %}` provides the content body via `caller()`. This is the idiomatic way to get block-driven slots into a macro. Child templates only need `{% block content %}`; `{% block breadcrumb %}` is optional.

### Design Tokens & Dimensions (v0.2.0)

These Tailwind v4 token classes are already defined via `@theme` in `ui/beeper_ui/static/css/input.css` (Story 3.1):

| Token | Class examples | Hex |
|---|---|---|
| surface-base | `bg-surface-base` | `#0f0f1a` (page bg) |
| surface-raised | `bg-surface-raised` | `#1a1a2e` (sidebar, top bar) |
| surface-overlay | `border-surface-overlay` | `#252540` (borders, dividers) |
| text-primary | `text-text-primary` | `#f8fafc` |
| text-secondary | `text-text-secondary` | `#94a3b8` (breadcrumb) |
| primary | `bg-primary` / `text-primary` ⚠ | `#6366f1` |

⚠ Note: the color token is named `primary`, so the class is `bg-primary`. The text-color token is `text-primary` → class `text-text-primary` (token name `text-primary` prefixed by the `text-` utility). Don't confuse `text-primary` (a color token) with the `text-` utility prefix.

Exact dimensions (FR43) — map to Tailwind classes:
| Element | Spec | Tailwind class |
|---|---|---|
| Sidebar expanded (≥1200px) | 256px | `lg:w-64` |
| Sidebar collapsed (<1200px) | 64px | `w-16` |
| Top bar height | 48px | `h-12` |
| Content padding | 24px | `p-6` |
| Sidebar transition | 200ms ease-in-out | `transition-[width] duration-200 ease-in-out` |

Breakpoints (configured in `input.css`, defaults cleared): `sm`=768px, `lg`=1200px, `xl`=1920px. The sidebar expands at the `lg` (1200px) breakpoint. [Source: ux-design-specification.md §Spacing/Breakpoints; epics.md Story 3.2]

### Preflight Is Disabled — Implications

Story 3.1 disabled Tailwind Preflight (no `@import "tailwindcss/preflight.css"`). Therefore **no CSS reset is applied** by Tailwind. Do not assume `margin: 0` on `<body>`, normalized `box-sizing`, or reset list/heading styles. The layout shell must set what it needs explicitly (e.g. ensure the root flex container fills the viewport; `overflow-x-hidden` on `<main>` guards AC2). [Source: 3-1 Completion Notes; input.css]

### Current `base.html` — What to Preserve

The rewrite must keep these intact (only the `<header>`/`<nav>`/`<main>` body region changes):
- `<head>`: `{% block title %}`, `htmx.min.js` script, `tailwind.css` link, `main.css` link (tailwind BEFORE main — specificity order).
- Before `</body>`: `{% include "components/_command_palette.html" %}`, `{% include "components/_keyboard_help.html" %}`, `command-palette.js` script, `{% block scripts %}{% endblock %}`.

The old `<header>` (logo `<h1>`, `<nav>` with 15 links, `.tagline`) and the `<main><div class="container">` wrapper are **removed** — replaced by the layout shell. The "Welcome to Beeper" default content currently inside `{% block content %}` can be preserved as the block default.

### Regression Risk — Existing Tests on the Top-Nav

Removing the old `<header>` nav **will break any test that asserts on it.** Before running the suite, grep the test suite for nav assertions and update them:
```bash
grep -rn 'header-content\|tagline\|/health/\|/topology/\|<nav>' ui/tests/
```
Likely-affected files: `test_app.py`, `test_routes.py`, `test_command_palette.py` (palette navigates routes), and any test asserting a specific nav link is present on a rendered page. Update these to assert against the new shell instead of deleting coverage. The 2,032-passing baseline is the contract — any net regression is a story blocker. [Source: 3-0d-ui-test-baseline.md; 3-1 Dev Notes "Previous Story Learnings"]

Also note: the old top-nav linked to `/health/`, `/slo/`, `/services/`, etc. Removing the nav does NOT remove those routes — pages remain reachable by URL. Navigation links return in Story 3.3's sidebar. A transient state where the app has no clickable nav between 3.2 and 3.3 is expected and acceptable within the epic (atomic migration is per-PR for the *shell*, navigation content is the next story).

### Testing Approach

- **Framework:** `pytest` + `respx` (mock operator at `http://mock-operator:8080`, set in `TestingConfig`). Pattern: `@respx.mock` + `client.get()` + HTML content assertions.
- **New tests:** add to a new file `ui/tests/test_layout_shell.py` (mirrors `test_tailwind_pipeline.py` from Story 3.1) — render `base.html` (directly or via any route) and assert shell structure, hamburger, logo, breadcrumb override, responsive sidebar classes, and command-palette/keyboard-help coexistence.
- **No visual regression tooling** — viewport checks at 768/1200/1920px are manual; note in completion notes if no browser is available in the environment.
- **Lint:** `ruff check .` with 100-char line length (Python only — Jinja/HTML not linted).

### Project Structure Notes

- New file: `ui/beeper_ui/templates/components/layout.html` (joins `_command_palette.html`, `_keyboard_help.html` in the existing `components/` dir). Note: `layout.html` has **no `_` prefix** — it is a macro-defining component, not an `{% include %}`d partial.
- Modified file: `ui/beeper_ui/templates/base.html`.
- New test file: `ui/tests/test_layout_shell.py`.
- No Python production code changes — templates and tests only. No new dependencies.
- No `tailwind.config.js` — Tailwind v4 is CSS-first; all config lives in `input.css`. (Story 3.1 ACs referenced v3 `tailwind.config.js`; the project uses v4 — do not create that file.)

### Previous Story Intelligence (Story 3.1)

- **Tailwind v4, not v3:** No `tailwind.config.js`. Config is `@theme` in `input.css`. Classes available: `bg-surface-base`, `bg-surface-raised`, `bg-surface-overlay`, `bg-primary`, `border-surface-overlay`, `text-text-primary`, etc.
- **Flask `url_for` does not check file existence** — tests pass even though the generated `tailwind.css` isn't built in CI. Template rendering tests work without running `make tailwind-build`.
- **Preflight intentionally disabled** to protect the 6,982-line `main.css`. No reset — see above.
- **Test pattern that worked:** file-existence + content-substring assertions for config; route-render + HTML assertions for templates. Code review on 3.1 flagged "fragile substring tests" — assert on meaningful, stable strings (e.g. a class combination or an element role), not brittle fragments.
- **Coexistence discipline:** 3.1's reviewer emphasized never mixing Tailwind + custom CSS on one element. The layout shell is a clean Tailwind-only surface — keep it that way.

### Git Intelligence

Recent commits confirm Epic 3 is mid-flight and Story 3.1 landed cleanly:
- `0896ba3 feat: install Tailwind CSS v4 build pipeline (Story 3.1)` — the pipeline this story builds on.
- `af452ff fix: achieve clean UI test baseline — 2,023 pass, 0 fail (Story 3.0d)` — the baseline (now 2,032 after 3.1's 9 new tests).
- Commit style: `feat:`/`fix:` prefix + short description + `(Story X.Y)` suffix. Follow this when committing.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.2 Implement Layout Shell & Base Template Migration]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-3 Layout Shell Template Inheritance Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-6 Sidebar State Management Approach]
- [Source: _bmad-output/planning-artifacts/architecture.md — Canonical Component Macro Files (components/layout.html = Component #1)]
- [Source: _bmad-output/planning-artifacts/architecture.md — Frontend Architecture, CSS coexistence rule]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — §Spacing, Breakpoints, Motion (v0.2.0 design system)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — §"Two navigation systems coexisting" anti-pattern, atomic deployment]
- [Source: _bmad-output/implementation-artifacts/3-1-install-tailwind-css-build-pipeline.md — Tailwind v4 pipeline, preflight disabled, test baseline]
- [Source: _bmad-output/implementation-artifacts/3-0d-ui-test-baseline.md — 2,023 passing tests baseline]

## Dev Agent Record

### Agent Model Used

(to be filled by dev agent)

### Debug Log References

### Completion Notes List

### File List
