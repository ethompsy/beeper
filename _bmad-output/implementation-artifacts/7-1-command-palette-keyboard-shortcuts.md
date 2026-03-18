# Story 7.1: Command Palette & Keyboard Shortcuts

Status: review

## Story

As a **user**,
I want to navigate the UI via keyboard shortcuts and a command palette (Cmd+K),
so that I can work at speed without reaching for the mouse during incidents.

## Acceptance Criteria

1. **Given** a user presses Cmd+K (or Ctrl+K) anywhere in the UI **When** the command palette opens **Then** a search input with ARIA combobox role is displayed, matching commands and navigation targets as the user types **And** the palette closes on Escape or clicking outside

2. **Given** the command palette is open **When** the user types a query (e.g., "inv" or "slo" or "hand") **Then** matching items are filtered in real-time: navigation targets, recent investigations, actions (e.g., "Request Handoff", "View SLO Dashboard") **And** the user can select with arrow keys + Enter

3. **Given** keyboard shortcuts are defined for common actions **When** a user presses a shortcut (e.g., `g i` for go-to-investigations, `g s` for go-to-SLO, `?` for shortcut help) **Then** the action executes immediately **And** shortcuts are discoverable via the `?` help overlay and the command palette

## Tasks / Subtasks

- [x] Task 1: Create command palette JavaScript module (AC: #1, #2)
  - [x] 1.1 Create `ui/beeper_ui/static/js/command-palette.js` as an IIFE module. Define a `COMMANDS` array containing all navigation targets (label, href, category="navigation", keywords) and action commands (label, action, category="action", keywords). Navigation targets: Investigations `/investigations/`, Knowledge Base `/knowledge/`, Sources `/sources/`, Health `/health/`, Metrics `/metrics/`, Spending `/spending/`, Cost Insights `/spending/costs`, SLO `/slo/`, Topology `/topology/`, Notifications `/notifications/`, Handoff `/handoff/`, Trust Settings `/settings/trust/`, Reports `/reports/`.
  - [x] 1.2 Implement `openPalette()`: show `#command-palette-overlay`, focus search input, set `aria-expanded="true"`, show all commands as default results. Implement `closePalette()`: hide overlay, clear input, set `aria-expanded="false"`, return focus to previously focused element.
  - [x] 1.3 Implement `filterCommands(query)`: case-insensitive match against command label and keywords. Group results by category: "Actions" first, then "Navigation". Return filtered+grouped list. If empty query, return all commands grouped.
  - [x] 1.4 Implement `renderResults(results)`: clear `#command-results`, for each group render a `<li role="presentation">` group header, then for each item render `<li role="option" id="cmd-{index}">` with label, optional shortcut badge, and category indicator. First item gets `aria-selected="true"`.
  - [x] 1.5 Implement keyboard navigation: Arrow Up/Down to move `aria-selected` and update `aria-activedescendant` on combobox input. Enter to execute selected command (navigate via `window.location.href` for nav items, call action handler for actions). Escape to close palette.
  - [x] 1.6 Implement input handler: on `input` event of search field, call `filterCommands()` then `renderResults()`. Debounce is not needed (all client-side filtering).

- [x] Task 2: Implement global keyboard shortcut registry (AC: #3)
  - [x] 2.1 In `command-palette.js`, implement a chord shortcut system. Track `pendingKey` state: when user presses `g`, set `pendingKey = "g"` and start a 500ms timeout. If second key pressed within timeout (e.g., `i`), execute the chord action and clear pending. If timeout expires, clear pending. Shortcuts: `g i` → `/investigations/`, `g s` → `/slo/`, `g k` → `/knowledge/`, `g n` → `/notifications/`, `g t` → `/topology/`, `g h` → `/health/`, `g m` → `/metrics/`.
  - [x] 2.2 Implement single-key shortcut `?` to toggle the keyboard help overlay (`#keyboard-help-overlay`). Do NOT fire shortcuts when focus is on `input`, `textarea`, or `select` elements (same guard as investigation-collab.js pattern).
  - [x] 2.3 Listen for `Cmd+K` (metaKey+k on Mac) and `Ctrl+K` (ctrlKey+k) globally. Call `e.preventDefault()` and `openPalette()`. These shortcuts work even when focused on inputs.
  - [x] 2.4 Ensure no conflicts with existing shortcuts in `investigation-collab.js` (n, r, a, x). The global listener should check if the command palette is open before processing shortcuts — if palette is open, only palette shortcuts (arrows, enter, escape) should fire.

- [x] Task 3: Create command palette HTML template (AC: #1)
  - [x] 3.1 Create `ui/beeper_ui/templates/components/_command_palette.html`. Structure: overlay div (`#command-palette-overlay`, hidden by default, `class="command-palette-overlay"`), inner container div (`class="command-palette"`), search input (`id="command-search"`, `type="text"`, `role="combobox"`, `aria-label="Search commands and navigation"`, `aria-autocomplete="list"`, `aria-expanded="false"`, `aria-owns="command-results"`, `placeholder="Type a command or search..."`), results list (`ul#command-results`, `role="listbox"`).
  - [x] 3.2 Create `ui/beeper_ui/templates/components/_keyboard_help.html`. Structure: overlay div (`#keyboard-help-overlay`, hidden by default), inner container with table of all shortcuts: section "Navigation" (g i, g s, g k, g n, g t, g h, g m), section "Command Palette" (Cmd/Ctrl+K to open, arrows to navigate, Enter to select, Esc to close), section "Investigation" (n annotate, r redirect, a approve, x reject — reference existing). Close button and Escape to dismiss.

- [x] Task 4: Integrate command palette into base template (AC: #1, #3)
  - [x] 4.1 In `ui/beeper_ui/templates/base.html`, include `{% include "components/_command_palette.html" %}` and `{% include "components/_keyboard_help.html" %}` just before `</body>`. Add `<script src="{{ url_for('static', filename='js/command-palette.js') }}"></script>` in the scripts section (after htmx).

- [x] Task 5: Add command palette CSS styles (AC: #1, #2, #3)
  - [x] 5.1 In `ui/beeper_ui/static/css/main.css`, add command palette overlay styles: `.command-palette-overlay` — fixed position, full viewport, background `rgba(0, 0, 0, 0.6)`, backdrop-filter blur(4px), z-index 1000, flexbox centering, `display: none` by default, `display: flex` when `.active`. `.command-palette` — width 600px, max-height 400px, background #1a1a2e (surface-raised), border 1px solid #333355 (border-subtle), border-radius 12px, overflow hidden, box-shadow.
  - [x] 5.2 Add search input styles: `.command-palette input` — full width, padding 16px, background transparent, color #f1f5f9 (text-primary), border-bottom 1px solid #333355, font-size 1rem, outline none. Focus: border-color #6366f1 (border-focus).
  - [x] 5.3 Add results list styles: `.command-results` — list-style none, max-height 320px, overflow-y auto, padding 8px. `.command-result-item` — padding 10px 16px, cursor pointer, border-radius 6px, display flex, justify-content space-between. `.command-result-item[aria-selected="true"]` and `.command-result-item:hover` — background #252540 (surface-elevated). `.command-result-group` — color #94a3b8 (text-secondary), font-size 0.75rem, text-transform uppercase, padding 8px 16px. `.command-shortcut-badge` — background #252540, color #94a3b8, padding 2px 6px, border-radius 4px, font-family monospace, font-size 0.75rem.
  - [x] 5.4 Add keyboard help overlay styles: `.keyboard-help-overlay` — same positioning as command palette overlay. `.keyboard-help` — width 500px, background #1a1a2e, border-radius 12px, padding 24px. `.keyboard-help table` — width 100%, color #f1f5f9. `.keyboard-help kbd` — background #252540, border 1px solid #333355, border-radius 4px, padding 2px 8px, font-family monospace, font-size 0.85rem.
  - [x] 5.5 Add `prefers-reduced-motion` support: no transition animations on open/close, instant display.

- [x] Task 6: Write command palette tests (AC: #1, #2, #3)
  - [x] 6.1 Create `ui/tests/test_command_palette.py`. Test command palette template inclusion: `test_base_template_includes_command_palette()` — GET `/` with FlaskClient, verify response contains `id="command-palette-overlay"` and `id="keyboard-help-overlay"` and `command-palette.js` script tag.
  - [x] 6.2 Test template structure: `test_command_palette_has_aria_combobox()` — verify `role="combobox"`, `aria-owns="command-results"`, `aria-autocomplete="list"`, `aria-label` attributes are present.
  - [x] 6.3 Test keyboard help template: `test_keyboard_help_contains_shortcuts()` — verify help overlay contains all shortcut key references (g i, g s, Cmd+K, ?, etc.).
  - [x] 6.4 Test command palette static file exists: `test_command_palette_js_exists()` — verify `ui/beeper_ui/static/js/command-palette.js` file exists.

- [x] Task 7: Run full test suite across all components (AC: all)
  - [x] 7.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x] 7.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x] 7.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x] 7.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x] 7.5 Run operator tests: `cd operator && cargo test`
  - [x] 7.6 Verify no regressions from baseline (3,332 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR47 maps to:** Command palette (Cmd+K) — UI-only feature. No investigator or operator changes needed. [Source: _bmad-output/planning-artifacts/epics.md#Story 7.1, architecture.md FR47]

**What already exists (DO NOT rebuild):**
- Keyboard shortcut pattern in `ui/beeper_ui/static/js/investigation-collab.js:346-364` — single-key shortcuts (n, r, a, x) with input field guard (`tagName` check for input/textarea/select)
- HTMX library loaded in `base.html` — use for any dynamic content loading
- Flask-SocketIO for real-time in `ui/beeper_ui/websocket/` — NOT needed for command palette
- Dark theme CSS in `ui/beeper_ui/static/css/main.css` — colors: surface-base #0f0f1a, surface-raised #1a1a2e, surface-elevated #252540, border-subtle #333355, border-focus #6366f1, text-primary #f1f5f9, text-secondary #94a3b8
- Navigation structure in `ui/beeper_ui/templates/base.html` — 12 routes in header `<nav>`: Investigations, Knowledge Base, Sources, Health, Metrics, Spending, Cost Insights, SLO, Topology, Notifications, Handoff, Trust
- Blueprint registration pattern in `ui/beeper_ui/routes/__init__.py`
- Reports route at `/reports/` (`ui/beeper_ui/routes/reports.py`)

**What this story adds:**
1. New `command-palette.js` — IIFE module with command registry, palette open/close, filtering, keyboard navigation, chord shortcuts (g+i, g+s, etc.), and help overlay toggle (?)
2. New `_command_palette.html` template — ARIA-compliant combobox with search + results listbox
3. New `_keyboard_help.html` template — shortcut help overlay with table of all shortcuts
4. CSS styles in main.css — command palette overlay, search input, results list, help overlay
5. Integration into `base.html` — template includes + script tag

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| Keyboard shortcut guard | `investigation-collab.js:348-349` | `tagName` check for input/textarea/select before firing shortcuts |
| HTMX | `base.html:7` | Already loaded, use for any HTMX-powered search if needed |
| Dark theme palette | `main.css` (throughout) | Colors: #0f0f1a, #1a1a2e, #252540, #333355, #6366f1, #f1f5f9, #94a3b8 |
| Navigation routes | `base.html:15-27` | 12 routes to register as command palette navigation targets |
| Flask test client | `ui/tests/conftest.py` | `client` fixture for route testing |
| Template render test pattern | `ui/tests/test_change_event_template.py` | `_render_template()` helper |

### Anti-Patterns to AVOID

- Do NOT use a JS framework (React, Vue, etc.) — the project uses vanilla JS exclusively
- Do NOT modify `investigation-collab.js` — add new shortcuts via the new command-palette.js module
- Do NOT create a Flask route for search — all filtering is client-side (navigation targets + actions are static)
- Do NOT use WebSockets for command palette — it's a static local-filter feature
- Do NOT add dependencies (no npm, no bundler) — vanilla JS only
- Do NOT add Qdrant semantic search — story scope is navigation + action commands only (KB search is separate)
- Do NOT modify the operator or investigator components — this is a UI-only feature
- Do NOT use opacity transitions if `prefers-reduced-motion` is set
- Do NOT break existing keyboard shortcuts (n, r, a, x) in investigation-collab.js — ensure no conflicts

### Previous Story Intelligence (6-9)

**Key learnings from Story 6-9 (Change Event Ingestion & Correlation):**
- Template partials use `{% if data %}...{% elif fallback %}...{% endif %}` pattern
- CSS follows dark-theme palette: red (#f87171), amber (#fbbf24), blue (#60a5fa), green (#34d399)
- All 3,332 tests pass (1,013 investigator + 1,788 UI + 531 operator)
- Test patterns: direct template rendering for UI tests, Flask client GET for route tests
- HTMX SSE pattern: `sse-swap="event-name"` attribute on div for live updates

### Git Intelligence

**Recent commits (last 5):**
- `dca5fcc` fix: wave-4 pre-flight (mypy overrides + test-only import fix)
- `b4da790` MAESTRO: epic-6 retrospective done
- `2aff595` MAESTRO: 6-9 done
- `e151660` MAESTRO: implement story 6-9 (Change Event Ingestion & Correlation)
- `7c84ae3` MAESTRO: 6-8 done

**Patterns observed:**
- UI-only features modify: templates, static JS/CSS, routes (optional), tests
- CSS additions go at the end of `main.css`
- Template partials in feature-specific folders or `components/` folder
- Tests in `ui/tests/` follow `test_{feature_name}.py` naming

### Testing Standards

- **Framework:** pytest with Flask test client
- **Test locations:**
  - `ui/tests/test_command_palette.py` — Command palette template + integration tests (NEW)
- **Patterns:**
  - `client.get("/")` to test base template includes
  - `assert b"expected_id" in response.data` for HTML element presence
  - `_render_template()` helper for isolated template tests
- **No frontend JS testing framework** — JS is tested via template integration tests (verify HTML structure and attributes)

### Project Structure Notes

**Files to CREATE:**
- `ui/beeper_ui/static/js/command-palette.js` — Command palette + keyboard shortcuts IIFE module
- `ui/beeper_ui/templates/components/_command_palette.html` — Command palette template
- `ui/beeper_ui/templates/components/_keyboard_help.html` — Keyboard shortcut help overlay
- `ui/tests/test_command_palette.py` — Command palette tests

**Files to MODIFY:**
- `ui/beeper_ui/templates/base.html` — Include command palette + help templates + script tag
- `ui/beeper_ui/static/css/main.css` — Add command palette + help overlay styles

**Files to NOT touch:**
- `investigator/**` — No investigator changes needed
- `operator/**` — No operator changes needed
- `ui/beeper_ui/static/js/investigation-collab.js` — Don't modify existing shortcuts
- `ui/beeper_ui/routes/*.py` — No route changes (all client-side)
- `ui/beeper_ui/services/*.py` — No service changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.1] — Acceptance criteria (lines 1329-1350)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR47] — Command palette requirement
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Command palette design, ARIA requirements, WCAG 2.1 AA
- [Source: ui/beeper_ui/static/js/investigation-collab.js:346-364] — Existing keyboard shortcut pattern
- [Source: ui/beeper_ui/templates/base.html] — Navigation structure, script loading
- [Source: ui/beeper_ui/static/css/main.css] — Dark theme color palette
- [Source: ui/beeper_ui/routes/__init__.py] — Blueprint registration pattern

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- All 7 tasks implemented successfully as a UI-only feature (no investigator/operator changes)
- IIFE command palette module with 17 commands (13 navigation + 4 action), client-side filtering, ARIA combobox
- Chord shortcuts (g+i, g+s, g+k, g+n, g+t, g+h, g+m) with 500ms timeout, input field guard
- Cmd+K / Ctrl+K opens palette from anywhere including input fields, ? toggles help overlay
- No conflicts with existing investigation-collab.js shortcuts (n, r, a, x) — palette intercepts when open
- Dark theme CSS with backdrop blur, surface-raised colors, focus ring, kbd elements
- prefers-reduced-motion: disables backdrop-filter for accessibility
- 23 new tests: 3 inclusion, 7 ARIA, 6 help, 4 static file, 3 CSS integration
- Test results: 1,013 investigator + 1,811 UI + 531 operator = **3,355 tests passing** (up from 3,332)

### File List

**Created:**
- `ui/beeper_ui/static/js/command-palette.js`
- `ui/beeper_ui/templates/components/_command_palette.html`
- `ui/beeper_ui/templates/components/_keyboard_help.html`
- `ui/tests/test_command_palette.py`

**Modified:**
- `ui/beeper_ui/templates/base.html`
- `ui/beeper_ui/static/css/main.css`
