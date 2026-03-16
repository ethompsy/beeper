# Story 3.3: Confidence Gate Threshold Configuration

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an **admin**,
I want to configure confidence gate thresholds per trust level via the settings UI,
so that I can tune how much evidence Beeper needs before acting autonomously.

## Acceptance Criteria

1. **Given** the trust configuration UI page (`/settings/trust`)
   **When** an admin views the page
   **Then** current gate thresholds are displayed per trust level (TL3, TL4, TL5) with explanations of each level's behavior
   **And** the admin can adjust thresholds with an input field (0.0-1.0 range)
   **And** TL1-2 are shown as "Advisory Only" with no threshold configuration

2. **Given** an admin adjusts a threshold via the UI form
   **When** the form is submitted
   **Then** the threshold is persisted via the existing `ConfidenceGateService.set_gate_threshold()` and immediately effective
   **And** the UI updates inline (HTMX) showing the new threshold with a success message
   **And** the endpoint requires `@require_role("admin")` (NFR12)

3. **Given** a threshold is set to an unreasonable value (e.g., < 0.0 or > 1.0, non-numeric, boolean)
   **When** the admin submits the change
   **Then** validation rejects the value with a clear error message rendered in the HTMX partial

## Tasks / Subtasks

- [x] Task 1: Add gate threshold display section to trust settings page (AC: #1)
  - [x] 1.1 Create `ui/beeper_ui/templates/trust/_gate_thresholds.html` — HTMX partial showing gate threshold cards for TL3, TL4, TL5
  - [x] 1.2 Each card shows: trust level badge, level name, current threshold as percentage, behavior description ("Actions require X% confidence"), last updated info
  - [x] 1.3 TL1-2 note: display a brief info line "Trust levels 1-2 are advisory-only — no confidence gate applies"
  - [x] 1.4 Admin controls per card: number input (step="0.01", min="0.01", max="1.0"), submit button
  - [x] 1.5 Include `_gate_thresholds.html` in `trust/settings.html` after the service list and before the reference table

- [x] Task 2: Add gate threshold update UI route (AC: #2, #3)
  - [x] 2.1 Add `GET /settings/trust/gates` route to `trust_settings.py` — returns `_gate_thresholds.html` partial with current thresholds from `ConfidenceGateService.get_gate_thresholds()`, decorated with `@require_role("user")`
  - [x] 2.2 Add `POST /settings/trust/gates/<int:trust_level>/update` route to `trust_settings.py` — form submission to update threshold, decorated with `@require_role("admin")`
  - [x] 2.3 Create `ui/beeper_ui/templates/trust/_gate_update_result.html` — HTMX partial for gate threshold update result (replaces individual card inline)
  - [x] 2.4 Validate threshold: reject boolean, non-numeric, < 0.0, > 1.0 with error in `_gate_update_result.html`
  - [x] 2.5 Validate trust_level: reject levels outside 3-5 with error
  - [x] 2.6 On success: call `ConfidenceGateService.set_gate_threshold()`, render updated card with success message

- [x] Task 3: Comprehensive testing (AC: #1, #2, #3)
  - [x] 3.1 Create `ui/tests/test_gate_threshold_settings.py` — UI route tests:
    - Test GET /settings/trust/gates returns HTMX partial with threshold data
    - Test GET /settings/trust/gates shows all three TL3/TL4/TL5 thresholds
    - Test POST update with valid threshold → 200 + success partial
    - Test POST update with threshold > 1.0 → error partial
    - Test POST update with threshold < 0.0 → error partial
    - Test POST update with non-numeric threshold → error partial
    - Test POST update with boolean threshold → error partial
    - Test POST update for TL1 → error (advisory-only)
    - Test POST update for TL2 → error (advisory-only)
    - Test POST update requires admin role
    - Test GET gate thresholds accessible by user role
    - Test full settings page includes gate thresholds section
    - Test Qdrant error returns graceful error display
  - [x] 3.2 Run full UI test suite — verify zero regressions
  - [x] 3.3 Run ruff lint on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: Story 3-2 already implemented the FULL backend.** The confidence gate engine, API routes, and Qdrant storage are all in place. Story 3-3 adds ONLY the UI settings page for threshold configuration — analogous to how story 3-1 had separate API (`trust_config.py`) and UI (`trust_settings.py`) routes.

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `ConfidenceGateService` | `ui/beeper_ui/services/confidence_gate_service.py` | Done (story 3-2) |
| `get_gate_thresholds()` | Returns all TL3-5 configs | Done |
| `get_gate_threshold(tl)` | Returns single config | Done |
| `set_gate_threshold(tl, threshold, updated_by)` | Persists to Qdrant | Done |
| API GET `/api/v1/trust/gates` | Lists thresholds | Done |
| API PUT `/api/v1/trust/gates/<tl>` | Updates threshold (admin) | Done |
| `ConfidenceGateConfig` dataclass | trust_level, threshold, updated_by, updated_at, description | Done |
| `ConfidenceGateError` exception | For error handling | Done |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `_gate_thresholds.html` template | HTMX partial for threshold cards |
| `_gate_update_result.html` template | HTMX partial for update result |
| `GET /settings/trust/gates` route | UI route to serve threshold partial |
| `POST /settings/trust/gates/<tl>/update` route | UI route for form submission |
| Integration in `settings.html` | Include gate threshold section |

**UI Route Pattern (follow `trust_settings.py`):**
```python
@trust_settings_bp.route("/gates")
@require_role("user")
def gate_thresholds_section() -> str:
    """Display gate thresholds section."""
    service = _get_gate_service()
    try:
        thresholds = service.get_gate_thresholds()
    except ConfidenceGateError:
        thresholds = []
        error_message = "Unable to load gate threshold data"
    finally:
        service.close()
    return render_template("trust/_gate_thresholds.html", thresholds=thresholds, ...)

@trust_settings_bp.route("/gates/<int:trust_level>/update", methods=["POST"])
@require_role("admin")
def update_gate_threshold(trust_level: int) -> str:
    """Handle form submission to update gate threshold."""
    ...
```

**HTMX Pattern (follow `_service_list.html` and `_update_result.html`):**
```html
<div class="card gate-card" id="gate-card-tl{{ config.trust_level }}">
    <div class="gate-card-header">
        <span class="badge trust-tl{{ config.trust_level }}">TL{{ config.trust_level }}</span>
        <h3>{{ config.description }}</h3>
    </div>
    <div class="gate-card-body">
        <p>Threshold: <strong>{{ (config.threshold * 100)|int }}%</strong></p>
    </div>
    <div class="gate-card-actions">
        <form hx-post="/settings/trust/gates/{{ config.trust_level }}/update"
              hx-target="#gate-card-tl{{ config.trust_level }}"
              hx-swap="outerHTML">
            <input type="number" name="threshold" step="0.01" min="0.01" max="1.0"
                   value="{{ config.threshold }}">
            <button type="submit" class="btn btn-primary btn-sm">Update</button>
        </form>
    </div>
</div>
```

**Integration in `settings.html`:**
```html
<!-- After service list section, before reference table -->
<div class="card" style="margin-top: 20px;">
    <h3>Confidence Gate Thresholds</h3>
    <p>Configure the minimum confidence required for autonomous actions at each trust level.</p>
    <div id="gate-thresholds"
         hx-get="/settings/trust/gates"
         hx-trigger="load"
         hx-swap="innerHTML">
        <span class="htmx-indicator">Loading gate thresholds...</span>
    </div>
</div>
```

### Service Dependency

Import `ConfidenceGateService` and `ConfidenceGateError` in `trust_settings.py`:
```python
from beeper_ui.services.confidence_gate_service import (
    ConfidenceGateService,
    ConfidenceGateError,
    GATED_TRUST_LEVELS,
    MIN_GATED_LEVEL,
    MAX_GATED_LEVEL,
)
```

Create a `_get_gate_service()` helper in `trust_settings.py` (same pattern as `_get_trust_level_service()`):
```python
def _get_gate_service() -> ConfidenceGateService:
    return ConfidenceGateService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )
```

### Critical Guardrails

- **No new pip dependencies** — reuse existing ConfidenceGateService
- **No new API routes** — only add UI routes to existing `trust_settings_bp` Blueprint
- **No new Blueprints** — add routes to existing `trust_settings_bp` in `trust_settings.py`
- **Reuse ConfidenceGateService** — call existing `get_gate_thresholds()` and `set_gate_threshold()`, DO NOT re-implement backend logic
- **Follow HTMX patterns** — server renders HTML, HTMX swaps partials, no client-side JS
- **Permission model** — `@require_role("user")` for viewing thresholds, `@require_role("admin")` for updating
- **Error handling** — Qdrant unreachable should show graceful error in partial, not crash
- **No Tailwind** — use existing `main.css` BEM classes (`.card`, `.badge`, `.btn`, `.trust-tl*`)
- **Test isolation** — mock all ConfidenceGateService calls in tests
- **Boolean validation** — check `isinstance(threshold, bool)` before `isinstance(threshold, (int, float))` (lesson from story 3-1)
- **Identity** — read `X-Beeper-User` header for `updated_by` (existing pattern)
- **Threshold range** — validate 0.0-1.0 with clear error messages

### Project Structure Notes

- Trust settings routes: `ui/beeper_ui/routes/trust_settings.py` (modify — add gate threshold routes)
- Trust settings templates: `ui/beeper_ui/templates/trust/` (add new partials)
- Confidence gate service: `ui/beeper_ui/services/confidence_gate_service.py` (DO NOT modify — reuse as-is)
- Confidence gate API routes: `ui/beeper_ui/routes/confidence_gates.py` (DO NOT modify — already complete)
- Trust settings full page: `ui/beeper_ui/templates/trust/settings.html` (modify — add gate section)
- All tests: `ui/tests/` (add new test file)

### Previous Story Intelligence

**From Story 3-2 (Confidence Gate Engine):**
- `ConfidenceGateService` is fully implemented with get/set/list threshold methods
- `ConfidenceGateConfig` dataclass: trust_level, threshold, updated_by, updated_at, description
- API routes at `/api/v1/trust/gates` already handle validation (0.0-1.0 range, TL3-5 only)
- `GATED_TRUST_LEVELS = {3, 4, 5}` constant available for iteration
- `ConfidenceGateError` exception for error handling
- Default thresholds: TL3=90%, TL4=85%, TL5=80%
- 66 tests passing for gate service and API routes (no regressions)

**From Story 3-1 (Trust Level Configuration & Persistence):**
- `trust_settings.py` is the UI Blueprint for trust settings — add gate routes here
- HTMX partial pattern: full page detects `HX-Request` header, returns partial or full page
- `_update_result.html` pattern: success shows updated card, error shows error card
- Service lifecycle: `_get_service()` → try/except/finally: service.close()
- Form uses `request.form.get()` for POST data
- `X-Beeper-User` header for identity

**From Story 3-1/3-2 code review fixes:**
- Boolean bypass in validation — `isinstance(value, bool)` check before `isinstance(value, (int, float))`
- `os.getenv("QDRANT_HOST", "localhost")` with default
- Avoid redundant exception clauses

### Git Intelligence

Recent commits: `MAESTRO: 3-2 done` → `MAESTRO: implement story 3-2 (Confidence Gate Engine)`. Follow commit pattern: `MAESTRO: implement story 3-3 (Confidence Gate Threshold Configuration)`. Current test count: UI ~1172 passed. Investigator: 505 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.3] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#FR22] — "Admins can configure confidence gate thresholds per trust level"
- [Source: _bmad-output/planning-artifacts/epics.md#NFR12] — "Admin-only for trust level and confidence gate configuration"
- [Source: ui/beeper_ui/services/confidence_gate_service.py] — ConfidenceGateService (full backend, DO NOT modify)
- [Source: ui/beeper_ui/routes/confidence_gates.py] — API routes (already complete, DO NOT modify)
- [Source: ui/beeper_ui/routes/trust_settings.py] — UI Blueprint to extend with gate routes
- [Source: ui/beeper_ui/templates/trust/settings.html] — Full page to add gate section
- [Source: ui/beeper_ui/templates/trust/_service_list.html] — HTMX card pattern to follow
- [Source: ui/beeper_ui/templates/trust/_update_result.html] — Update result partial pattern to follow
- [Source: _bmad-output/implementation-artifacts/3-2-confidence-gate-engine.md] — Story 3-2 patterns and learnings
- [Source: _bmad-output/implementation-artifacts/3-1-trust-level-configuration-persistence.md] — Story 3-1 patterns and learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added gate threshold configuration UI to existing `/settings/trust/` page
- Created `_gate_thresholds.html` HTMX partial displaying TL3/TL4/TL5 threshold cards with badges, percentages, behavior descriptions, and update forms
- Created `_gate_update_result.html` HTMX partial for inline update results (success/error)
- Added `GET /settings/trust/gates` route — serves threshold partial via `ConfidenceGateService.get_gate_thresholds()`
- Added `POST /settings/trust/gates/<int:trust_level>/update` route — form submission for threshold updates via `ConfidenceGateService.set_gate_threshold()`
- `@require_role("user")` for viewing, `@require_role("admin")` for updating (NFR12)
- Validation: rejects non-numeric, < 0.0, > 1.0, and advisory-only TL1-2 with clear error messages
- Integrated gate section in `settings.html` with HTMX lazy-load between service list and reference table
- No new Blueprints, no new pip dependencies, no backend modifications — reuses story 3-2's complete backend
- 23 new tests (9 GET section + 14 POST update), all passing
- Full UI suite: 1195 passed (1172 existing + 23 new), zero regressions
- Ruff lint: all clean on new/modified Python files

### File List

**New files created:**
1. `ui/beeper_ui/templates/trust/_gate_thresholds.html` — HTMX partial for gate threshold cards display
2. `ui/beeper_ui/templates/trust/_gate_update_result.html` — HTMX partial for gate threshold update result
3. `ui/tests/test_gate_threshold_settings.py` — 23 UI route tests for gate threshold settings

**Files modified:**
1. `ui/beeper_ui/routes/trust_settings.py` — Added `_get_gate_service()`, `gate_thresholds_section()`, `update_gate_threshold()` routes + ConfidenceGateService imports
2. `ui/beeper_ui/templates/trust/settings.html` — Added "Confidence Gate Thresholds" section with HTMX lazy-load
3. `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 3-3 status updates
4. `_bmad-output/implementation-artifacts/3-3-confidence-gate-threshold-configuration.md` — This story file
