# Story 3.1: Install Tailwind CSS Build Pipeline

Status: done

## Story

As a **developer**,
I want the Tailwind CSS standalone binary integrated into the build pipeline,
So that new UI components can use Tailwind utility classes alongside the existing CSS.

## Background

**Origin:** Epic 3 (UI Layout Shell & Sidebar Navigation) — first proper story after all preparation tasks (3-0a through 3-0h) are complete. This story establishes the CSS build infrastructure that Stories 3.2–3.4 depend on.

**Current State:** The UI has 6,982 lines of custom CSS in `ui/beeper_ui/static/css/main.css`. There is NO Node.js, npm, or any JavaScript build tooling in the project. The frontend is Flask + Jinja2 + HTMX with vanilla JS.

**Architecture Decision AD-7:** Use Tailwind CSS standalone binary (no Node.js dependency). Integrate via Makefile targets and UI Dockerfile build stage.

## Acceptance Criteria

1. **Given** the UI project at `ui/`
   **When** Tailwind CLI standalone binary is added to the project
   **Then** `make tailwind-watch` runs `tailwindcss --watch` for development with output to `ui/beeper_ui/static/css/tailwind.css`
   **And** `make tailwind-build` runs `tailwindcss --minify` for production builds

2. **Given** the Tailwind config file `ui/tailwind.config.js`
   **When** the config is created
   **Then** it includes the v0.2.0 design tokens (surface-base, surface-raised, surface-overlay, primary, status colors, text hierarchy) as theme extensions
   **And** content paths are set to `['./beeper_ui/templates/**/*.html', './beeper_ui/static/js/**/*.js']` for tree-shaking
   **And** breakpoints are configured: sm=768px, lg=1200px, xl=1920px

3. **Given** the Tailwind input file `ui/beeper_ui/static/css/input.css`
   **When** it is created with `@tailwind base; @tailwind components; @tailwind utilities;`
   **Then** the generated `tailwind.css` is added to `.gitignore` (build output, not source)

4. **Given** the UI Dockerfile
   **When** a production image is built
   **Then** Tailwind CLI runs minification as a build stage and the output CSS is included in the final image

5. **Given** the base template `ui/beeper_ui/templates/base.html`
   **When** it is updated
   **Then** it includes the `tailwind.css` stylesheet link alongside the existing `main.css`
   **And** existing page rendering is visually unchanged (Tailwind reset does not break existing styles)

## Tasks / Subtasks

- [x] Task 1: Download and configure Tailwind CSS standalone binary
  - [x] 1.1 Determine the correct Tailwind standalone CLI binary for the project (macOS arm64 for dev, linux-x64 for Docker)
  - [x] 1.2 Create `ui/beeper_ui/static/css/input.css` with Tailwind v4 CSS-first config (`@theme` directive) including design tokens and breakpoints per AC2
  - [x] 1.3 Create `ui/beeper_ui/static/css/input.css` with Tailwind v4 directives per AC3
  - [x] 1.4 Add `ui/beeper_ui/static/css/tailwind.css` to `.gitignore`
  - [x] 1.5 Verify `tailwindcss` CLI can generate output CSS from input.css + config

- [x] Task 2: Add Makefile targets
  - [x] 2.1 Add `tailwind-watch` target to root `Makefile`
  - [x] 2.2 Add `tailwind-build` target
  - [x] 2.3 Verify both targets execute correctly

- [x] Task 3: Update UI Dockerfile with Tailwind build stage
  - [x] 3.1 Add a Tailwind build stage that downloads the standalone CLI binary (linux-x64)
  - [x] 3.2 Copy `input.css` and template/JS source into the build stage
  - [x] 3.3 Run `tailwindcss --minify` to generate production CSS
  - [x] 3.4 Copy generated `tailwind.css` to the final image at `beeper_ui/static/css/tailwind.css`
  - [x] 3.5 Docker build not verifiable (daemon not running) — Dockerfile syntax validated

- [x] Task 4: Update base.html to include tailwind.css
  - [x] 4.1 Add `tailwind.css` link BEFORE `main.css` so existing styles take precedence
  - [x] 4.2 Preflight disabled by omitting `preflight.css` import in input.css (v4 approach)
  - [x] 4.3 All 2,032 UI tests pass (2,023 existing + 9 new)
  - [x] 4.4 Visual spot-check deferred (no browser in CI — manual step)

- [x] Task 5: Add tests and verify
  - [x] 5.1 Add test that `tailwind.css` link is present in rendered base template
  - [x] 5.2 Add test that `main.css` link is still present (coexistence)
  - [x] 5.3 Run full test suite: 2,032 passed in ~50s
  - [x] 5.4 Run linting: `ruff check` clean on new file
  - [x] 5.5 Verify `input.css` contains expected design tokens and breakpoints (9 tests)

## Dev Notes

### Architecture Reference

- **AD-7 (Tailwind Build Pipeline):** Standalone binary, `make tailwind-watch` for dev, `make tailwind-build` for production, UI Dockerfile build stage. [Source: _bmad-output/planning-artifacts/architecture.md — AD-7]
- **AD-3 (Layout Shell):** Story 3.2 will use the Tailwind pipeline established here. All 29 page templates inherit from `base.html`. [Source: _bmad-output/planning-artifacts/architecture.md — AD-3]
- **CSS Coexistence Rule (CRITICAL):** New components use Tailwind ONLY. Existing templates keep custom CSS until individually migrated. **NEVER mix Tailwind + custom CSS on the same HTML element.** [Source: _bmad-output/planning-artifacts/architecture.md]

### Design Tokens (v0.2.0)

These MUST be configured in `tailwind.config.js` as `theme.extend.colors`:

```javascript
colors: {
  'surface-base': '#0f0f1a',       // Page background (dark)
  'surface-raised': '#1a1a2e',     // Cards, raised surfaces
  'surface-overlay': '#252540',    // Overlays, dropdowns
  'primary': '#6366f1',            // Indigo (buttons, links)
  'primary-hover': '#818cf8',      // Primary hover state
  'status-healthy': '#22c55e',     // Green
  'status-warning': '#f59e0b',     // Amber
  'status-critical': '#ef4444',    // Red
  'status-muted': '#6b7280',       // Gray
  'text-primary': '#f8fafc',       // Primary text
  'text-secondary': '#94a3b8',     // Secondary text
  'text-muted': '#64748b',         // Muted text
}
```

Breakpoints as `theme.extend.screens`:
```javascript
screens: {
  'sm': '768px',
  'lg': '1200px',
  'xl': '1920px',
}
```

### Tailwind Standalone CLI

The standalone CLI binary does NOT require Node.js. Download from GitHub releases:
- **Dev (macOS arm64):** `tailwindcss-macos-arm64`
- **Docker (linux x64):** `tailwindcss-linux-x64`
- **GitHub:** `https://github.com/tailwindlabs/tailwindcss/releases`

Run pattern:
```bash
# Dev watch mode
./tailwindcss -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css --watch

# Production minification
./tailwindcss -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css --minify
```

### Current UI File Structure

```
ui/
├── Dockerfile                          # 2-stage build (builder → runtime)
├── pyproject.toml                      # Python deps (NO npm/node)
├── beeper_ui/
│   ├── app.py                          # Flask factory
│   ├── templates/
│   │   ├── base.html                   # Base layout (51 lines) — MODIFY HERE
│   │   ├── components/                 # Partial templates (2 files)
│   │   ├── investigations/             # 30 templates
│   │   ├── knowledge/                  # 29 templates
│   │   └── ... (18 route dirs total, 102 templates total)
│   └── static/
│       ├── css/
│       │   └── main.css                # 6,982 lines existing CSS — DO NOT MODIFY
│       └── js/
│           ├── htmx.min.js
│           ├── htmx-ext-sse.js
│           ├── command-palette.js
│           └── ...
└── tests/                              # 2,023 tests (66 files)
```

### Current base.html Structure

```html
<head>
    <script src="{{ url_for('static', filename='js/htmx.min.js') }}"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
</head>
```

Add `tailwind.css` BEFORE `main.css` so existing styles win on specificity conflicts:
```html
<head>
    <script src="{{ url_for('static', filename='js/htmx.min.js') }}"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
</head>
```

### Current Dockerfile Structure

```dockerfile
# Build stage — installs Poetry deps
FROM python:3.11-slim-bookworm AS builder
# ... poetry install ...

# Runtime stage
FROM python:3.11-slim-bookworm
# ... copy packages, copy app code ...
ENTRYPOINT ["flask", "run"]
```

Add Tailwind build stage BETWEEN builder and runtime:
```dockerfile
# Tailwind build stage
FROM alpine:3.19 AS tailwind
ADD https://github.com/tailwindlabs/tailwindcss/releases/download/v4.x.x/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss
COPY tailwind.config.js ./
COPY beeper_ui/static/css/input.css ./input.css
COPY beeper_ui/templates/ ./beeper_ui/templates/
RUN tailwindcss --minify -i input.css -o tailwind.css

# Runtime stage
COPY --from=tailwind /tailwind.css ./beeper_ui/static/css/tailwind.css
```

### Tailwind Preflight Reset Consideration

Tailwind's `@tailwind base` includes a CSS reset (Preflight) that can break existing styles. Options:
1. **Disable preflight:** Add `corePlugins: { preflight: false }` to `tailwind.config.js` — simplest, prevents any visual regression
2. **Keep preflight:** May require adjusting some existing styles — more work for this story

**Recommendation:** Disable preflight for this story. Re-enable later when migrating templates to Tailwind in Stories 3.2+.

### Makefile Integration

Current Makefile has targets at root level. New targets should follow existing patterns:
```makefile
# ── Tailwind CSS ──────────────────────────────────────────────────────────────

## Watch mode for development (generates CSS on file changes)
tailwind-watch:
	tailwindcss --watch -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css

## Production build (minified CSS)
tailwind-build:
	tailwindcss --minify -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css
```

Note: The Makefile assumes `tailwindcss` binary is on PATH. Developer must download it separately (documented in prerequisites).

### Testing Approach

- **Route tests:** Existing `@respx.mock` + `client.get()` tests verify template rendering. Add assertions for `tailwind.css` link presence.
- **No visual regression testing:** Not in scope — visual verification is manual.
- **Config validation:** Assert `tailwind.config.js` file exists and contains expected tokens (can be a simple file-existence + content check).

### Previous Story Learnings

**From Story 3-0d (UI Test Baseline):**
- 2,023 tests all passing — this is the baseline. Any regression = story blocker.
- Test patterns: `@respx.mock` + `client.get()` + HTML content assertions
- Mock operator URL: `http://mock-operator:8080` (set in `TestingConfig`)
- Linting: `ruff check .` with 100-char line length

**From Story 3-0g (Ollama/LiteLLM):**
- Shared utility pattern works well — create reusable modules rather than duplicating logic
- Order of operations matters for CSS (like parsing order mattered for JSON)

### Security Principle

No production Python code changes. Only new static files (CSS, JS config), Dockerfile changes, and Makefile targets. `tailwind.css` is a generated build artifact.

### CI/CD Impact

The `.github/workflows/ci.yml` runs `poetry run ruff check .` and `poetry run pytest` on `ui/`. Tailwind generation is NOT needed for tests (tests don't require CSS files to exist). The Dockerfile build stage handles production.

If tests try to render templates that reference `tailwind.css`, the static file must exist or Flask will 404. Consider creating a minimal placeholder or skipping the link in test mode.

### Project Structure Notes

- Config file `tailwind.config.js` lives at `ui/` root (same level as `pyproject.toml`)
- Input CSS at `ui/beeper_ui/static/css/input.css` (source, committed)
- Output CSS at `ui/beeper_ui/static/css/tailwind.css` (generated, gitignored)
- Binary NOT committed — downloaded per-developer and in Docker build stage

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — AD-7 Tailwind Build Pipeline]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-3 Layout Shell Strategy]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.1]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — Design tokens v0.2.0]
- [Source: _bmad-output/implementation-artifacts/3-0d-ui-test-baseline.md — 2,023 passing tests baseline]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References
N/A

### Completion Notes List

**Tailwind v4 Adaptation:** Story ACs were written for Tailwind v3 syntax (`tailwind.config.js`, `@tailwind base/components/utilities`). Implementation uses Tailwind v4.3.0 (current stable, released 2026-05-08) which has a CSS-first approach:
- `@import "tailwindcss/theme.css"` + `@import "tailwindcss/utilities.css"` replaces `@tailwind` directives
- `@theme { --color-*: ...; --breakpoint-*: ...; }` in CSS replaces `tailwind.config.js`
- No `tailwind.config.js` needed — all config lives in `input.css`
- Preflight disabled by omitting `@import "tailwindcss/preflight.css"` (v3 used `corePlugins: { preflight: false }`)
- Content paths auto-detected (v3 required explicit `content:` array)

**AC2 (Config):** Design tokens configured via `@theme` directive in `input.css` — all 12 colors + 3 breakpoints present. Functionally equivalent to v3 `tailwind.config.js` approach specified in AC.

**AC3 (Input CSS):** Uses v4 `@import` syntax instead of v3 `@tailwind` directives. Generated `tailwind.css` gitignored.

**AC4 (Dockerfile):** 3-stage build: builder (Poetry) → tailwind (Alpine + standalone CLI v4.3.0) → runtime. Downloads `tailwindcss-linux-x64` binary with SHA256 verification. Docker build not tested (daemon not running in dev environment).

**AC5 (base.html):** `tailwind.css` loaded before `main.css`. No preflight = no visual regression risk. Flask `url_for` generates URL without checking file existence, so tests pass without the generated CSS file.

**Test Results:**
| Metric | Story 3-0d Baseline | Story 3-1 Final |
|--------|---------------------|-----------------|
| Total | 2,023 | 2,032 |
| Passed | 2,023 | 2,032 |
| Failed | 0 | 0 |
| New Tests | — | 9 |
| Duration | ~50s | ~50s |

**Code Review Fixes (2026-05-13):**
- H1: Added `--breakpoint-*: initial` to clear default Tailwind breakpoints before custom ones — prevents `md` (768px) duplicating `sm` and `2xl` (1536px) creating out-of-order breakpoints
- M1: Added SHA256 checksum verification for Tailwind CLI binary download in Dockerfile
- M2: Added `WORKDIR /build` to Dockerfile tailwind stage, updated COPY path
- L1: Fixed fragile preflight test — checks for `tailwindcss/preflight.css` import instead of bare substring

### File List
- `ui/beeper_ui/static/css/input.css` — NEW: Tailwind v4 input with design tokens and breakpoints
- `ui/beeper_ui/templates/base.html` — MODIFIED: added tailwind.css link before main.css
- `ui/Dockerfile` — MODIFIED: added Tailwind build stage (alpine + standalone CLI, SHA256 verified)
- `Makefile` — MODIFIED: added tailwind-watch and tailwind-build targets
- `.gitignore` — MODIFIED: added ui/beeper_ui/static/css/tailwind.css
- `ui/tests/test_tailwind_pipeline.py` — NEW: 9 tests for CSS pipeline coexistence and config validation
