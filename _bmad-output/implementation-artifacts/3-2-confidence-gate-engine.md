# Story 3.2: Confidence Gate Engine

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to gate actions by confidence threshold so only sufficiently confident conclusions trigger actions,
so that Beeper doesn't act on uncertain evidence.

## Acceptance Criteria

1. **Given** an investigation reaches a conclusion with a confidence score (0.0-1.0)
   **When** the confidence gate evaluates the action
   **Then** the action is permitted only if the confidence score meets or exceeds the gate threshold for the service's trust level
   **And** below-threshold conclusions are presented as advisory recommendations only

2. **Given** the confidence gate thresholds per trust level (e.g., TL3 requires 0.90, TL4 requires 0.85, TL5 requires 0.80)
   **When** the same conclusion (confidence: 0.80) is evaluated for services at TL3 vs TL4
   **Then** the TL3 service gets an advisory recommendation while the TL4 service gets an automatic action
   **And** TL1 and TL2 always return advisory regardless of confidence score

3. **Given** an action is blocked by the confidence gate
   **When** the investigation result is displayed
   **Then** the UI shows "Confidence: 80% — below threshold (85%) for auto-action — advisory only"
   **And** the SRE can manually approve the action regardless

## Tasks / Subtasks

- [x] Task 1: Create ConfidenceGateService for gate evaluation logic (AC: #1, #2)
  - [x] 1.1 Create `ui/beeper_ui/services/confidence_gate_service.py` with `ConfidenceGateService` class
  - [x] 1.2 Define `GateDecision` dataclass: permitted (bool), confidence_score (float), threshold (float), trust_level (int), action_type (str: "autonomous"|"advisory"), reason (str), service_name (str)
  - [x] 1.3 Define `ConfidenceGateConfig` dataclass: trust_level (int), threshold (float 0.0-1.0), updated_by (str), updated_at (str), description (str)
  - [x] 1.4 Define `DEFAULT_GATE_THRESHOLDS` dict: {3: 0.90, 4: 0.85, 5: 0.80} — TL1-2 have no threshold (always advisory)
  - [x] 1.5 Implement `evaluate_gate(service_name, confidence_score, action_context) -> GateDecision` — core gate evaluation:
    - Fetch effective trust level from TrustLevelService
    - TL1-2: always return advisory (permitted=False, reason="Trust level {n} is advisory-only")
    - TL3-5: compare confidence_score against threshold for that trust level
    - Score >= threshold → permitted=True, action_type="autonomous"
    - Score < threshold → permitted=False, action_type="advisory", reason includes score vs threshold
  - [x] 1.6 Implement `get_gate_thresholds() -> list[ConfidenceGateConfig]` — returns all configured thresholds (from Qdrant or defaults)
  - [x] 1.7 Implement `get_gate_threshold(trust_level) -> ConfidenceGateConfig` — returns threshold for specific trust level
  - [x] 1.8 Implement `set_gate_threshold(trust_level, threshold, updated_by) -> ConfidenceGateConfig` — persists custom threshold to Qdrant, validates threshold 0.0-1.0 and trust_level 3-5
  - [x] 1.9 Store gate thresholds in `service_trust_levels` Qdrant collection using `gate_threshold_tl{n}` payload key pattern (consistent with autonomy_* field pattern from story 3-1)
  - [x] 1.10 Add `ConfidenceGateError` exception class
  - [x] 1.11 Implement `format_gate_message(decision: GateDecision) -> str` — produces human-readable messages like "Confidence: 80% — below threshold (85%) for auto-action — advisory only"

- [x] Task 2: Create confidence gate API routes (AC: #1, #2)
  - [x] 2.1 Create `ui/beeper_ui/routes/confidence_gates.py` with `confidence_gates_bp` Blueprint (url_prefix="/api/v1/trust/gates")
  - [x] 2.2 Add `POST /api/v1/trust/gates/evaluate` route — evaluates a confidence score for a given service, accepts JSON body `{"service_name": str, "confidence_score": float, "action_context": str|null}`, returns GateDecision as JSON, decorated with `@require_role("user")`
  - [x] 2.3 Add `GET /api/v1/trust/gates` route — lists all gate thresholds (defaults + custom), decorated with `@require_role("user")`
  - [x] 2.4 Add `GET /api/v1/trust/gates/<int:trust_level>` route — returns threshold for specific trust level, decorated with `@require_role("user")`
  - [x] 2.5 Add `PUT /api/v1/trust/gates/<int:trust_level>` route — updates threshold for trust level 3-5, decorated with `@require_role("admin")`, accepts JSON `{"threshold": float}`, validates 0.0-1.0 range and trust_level 3-5
  - [x] 2.6 Validate: reject PUT for TL1-2 with RFC 7807 error ("Trust levels 1-2 are advisory-only and have no confidence gate")
  - [x] 2.7 Validate: reject threshold values outside 0.0-1.0 with RFC 7807 error
  - [x] 2.8 Register `confidence_gates_bp` in `ui/beeper_ui/routes/__init__.py`

- [x] Task 3: Add confidence gate display to investigation detail UI (AC: #3)
  - [x] 3.1 Create `ui/beeper_ui/templates/investigations/_confidence_gate.html` — HTMX partial showing gate decision for an investigation
  - [x] 3.2 Gate display shows: confidence score percentage, threshold for service's trust level, gate decision (permitted/advisory), human-readable message from `format_gate_message()`
  - [x] 3.3 If gate blocks action: show "Advisory Only" badge with amber styling, display message like "Confidence: 80% — below threshold (85%) for auto-action — advisory only"
  - [x] 3.4 If gate permits action: show "Auto-action Eligible" badge with green styling
  - [x] 3.5 Add "Manual Approve" button when gate blocks — sends POST to existing `/investigations/<id>/confirm` endpoint (reuse existing approval flow)
  - [x] 3.6 Add gate evaluation route `GET /investigations/<id>/gate-status` to investigations.py — evaluates confidence gate for the investigation's service and confidence score, returns HTMX partial
  - [x] 3.7 Include `_confidence_gate.html` partial in investigation detail page (after recommendations section)

- [x] Task 4: Integrate confidence scoring normalization (AC: #1, #2)
  - [x] 4.1 Create `normalize_confidence_score(investigation_findings: dict) -> float` utility function in confidence_gate_service.py
  - [x] 4.2 Normalize investigator's mixed confidence formats to 0.0-1.0 scale:
    - RCA `confidence_percentage` (0-100) → divide by 100
    - Text levels "high"=0.85, "medium"=0.65, "low"=0.35
    - Missing confidence → 0.0 (safest default, advisory only)
  - [x] 4.3 Composite score: weighted average of available signals — RCA confidence (weight 0.5), signal correlation (weight 0.3), KB match quality (weight 0.2)
  - [x] 4.4 If only RCA confidence available, use it directly (no weighting with absent signals)

- [x] Task 5: Comprehensive testing (AC: #1, #2, #3)
  - [x] 5.1 Create `ui/tests/test_confidence_gate_service.py` — unit tests for ConfidenceGateService:
    - Test evaluate_gate with TL1 → always advisory
    - Test evaluate_gate with TL2 → always advisory
    - Test evaluate_gate with TL3 at 0.90 threshold: score=0.95 → permitted, score=0.85 → advisory
    - Test evaluate_gate with TL4 at 0.85 threshold: score=0.85 → permitted, score=0.80 → advisory
    - Test evaluate_gate with TL5 at 0.80 threshold: score=0.80 → permitted, score=0.75 → advisory
    - Test same confidence score yields different decisions at different trust levels (AC #2)
    - Test default thresholds used when no custom config
    - Test custom thresholds override defaults
    - Test get/set/list gate thresholds
    - Test threshold validation (reject <0.0, >1.0)
    - Test trust level validation (reject TL1-2 for set_gate_threshold)
    - Test normalize_confidence_score with RCA percentage
    - Test normalize_confidence_score with text levels
    - Test normalize_confidence_score with missing data → 0.0
    - Test composite score weighting
    - Test format_gate_message output strings
    - Test error handling (Qdrant unreachable)
    - Test unconfigured service defaults to TL1 → advisory
  - [x] 5.2 Create `ui/tests/test_confidence_gate_routes.py` — API route tests:
    - Test POST evaluate with valid data → 200 + GateDecision JSON
    - Test POST evaluate with missing service_name → 400 RFC 7807
    - Test POST evaluate with invalid confidence_score (negative, >1.0) → 400
    - Test GET gates → 200 + list of thresholds
    - Test GET gates/<trust_level> → 200 + single threshold
    - Test PUT gates/3 with valid threshold → 200 (admin)
    - Test PUT gates/1 → 400 RFC 7807 (advisory-only)
    - Test PUT gates/3 → 403 (user role, not admin)
    - Test PUT gates/3 with threshold >1.0 → 400
    - Test PUT gates/3 with threshold <0.0 → 400
  - [x] 5.3 Create `ui/tests/test_confidence_gate_ui.py` — UI template tests:
    - Test gate-status endpoint returns HTMX partial
    - Test advisory display shows correct message and badge
    - Test permitted display shows correct message and badge
    - Test manual approve button present when gate blocks
    - Test manual approve button absent when gate permits
  - [x] 5.4 Run full UI test suite — verify zero regressions
  - [x] 5.5 Run ruff lint + mypy on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This builds on Story 3-1's TrustLevelService.** The confidence gate engine evaluates whether an investigation's confidence score is high enough for autonomous action at the service's configured trust level. This is the enforcement mechanism that makes trust levels meaningful beyond configuration.

**Confidence Gate Logic:**

| Trust Level | Gate Behavior | Default Threshold |
|-------------|--------------|-------------------|
| TL1 (Advisory Only) | Always advisory — no gate evaluation needed | N/A |
| TL2 (Suggest with Evidence) | Always advisory — no gate evaluation needed | N/A |
| TL3 (Act with Approval) | Gate by confidence threshold | 0.90 (90%) |
| TL4 (Act and Notify) | Gate by confidence threshold | 0.85 (85%) |
| TL5 (Fully Autonomous) | Gate by confidence threshold | 0.80 (80%) |

**Architecture source:** "Each trust level has a configurable minimum confidence threshold (default: TL3=90%, TL4=85%, TL5=80%). Actions below threshold fall back to the next lower trust level's behavior." [Source: architecture.md#Confidence Gating Strategy]

**Confidence score is composite:** LLM confidence + KB match quality + signal correlation strength [Source: architecture.md#Confidence Gates]

**Service pattern** (follow `trust_level_service.py` — same Qdrant client lifecycle):
```python
@dataclass
class GateDecision:
    permitted: bool           # True = autonomous action allowed
    confidence_score: float   # 0.0-1.0 normalized
    threshold: float          # Gate threshold for this trust level
    trust_level: int          # Service's effective trust level
    action_type: str          # "autonomous" or "advisory"
    reason: str               # Human-readable explanation
    service_name: str

@dataclass
class ConfidenceGateConfig:
    trust_level: int          # 3, 4, or 5
    threshold: float          # 0.0-1.0
    updated_by: str           # Who set this threshold
    updated_at: str           # ISO 8601
    description: str          # Trust level name for display
```

**Route pattern** (follow `trust_config.py` Blueprint pattern):
```python
confidence_gates_bp = Blueprint("confidence_gates", __name__, url_prefix="/api/v1/trust/gates")
```

**Qdrant storage for gate thresholds** — use a single well-known point in `service_trust_levels` collection with a sentinel key like `__gate_thresholds__` as the service_name:
```python
{
    "service_name": "__gate_thresholds__",
    "gate_threshold_tl3": 0.90,
    "gate_threshold_tl4": 0.85,
    "gate_threshold_tl5": 0.80,
    "gate_updated_by": "admin@company.com",
    "gate_updated_at": "2026-03-16T10:30:00Z"
}
```

**Confidence score normalization** — the investigator uses mixed formats that must be unified:
- RCA hypothesis: `confidence_percentage: 0-100` (numeric) + `confidence_level: "high"|"medium"|"low"` (text)
- Resolution recommendations: `confidence: "high"|"medium"|"low"` (text only)
- Signal correlation: `confidence: "high"|"medium"|"low"` (text only)
- KB query: `confidence_boost: "high"|"medium"|null`

Normalization mapping:
```python
TEXT_CONFIDENCE_MAP = {"high": 0.85, "medium": 0.65, "low": 0.35}
COMPOSITE_WEIGHTS = {"rca": 0.5, "signal_correlation": 0.3, "kb_match": 0.2}
```

**RFC 7807 error format** (existing pattern):
```python
{"type": "about:blank", "title": "Bad Request", "status": 400, "detail": "Trust levels 1-2 are advisory-only and have no confidence gate"}
```

### Investigation Detail UI Integration

**Gate display component** — add after the recommendations section in investigation detail:
```html
<!-- Confidence Gate Status -->
<div class="card" id="gate-status"
     hx-get="/investigations/{{ investigation.id }}/gate-status"
     hx-trigger="load"
     hx-swap="innerHTML">
    <div class="htmx-indicator">Evaluating confidence gate...</div>
</div>
```

**Advisory display (gate blocks):**
- Amber badge: "Advisory Only"
- Message: "Confidence: 80% — below threshold (85%) for auto-action — advisory only"
- "Manual Approve" button → POST to existing `/investigations/<id>/confirm`

**Permitted display (gate allows):**
- Green badge: "Auto-action Eligible"
- Message: "Confidence: 95% — meets threshold (90%) for autonomous action"

**UX source:** "0-40%: status-critical red, 41-70%: status-warning amber, 71-90%: status-info blue → primary indigo, 91-100%: status-healthy green" [Source: ux-design-specification.md#Confidence Gates]

### Critical Guardrails

- **No new pip dependencies** — use qdrant-client (existing) for Qdrant operations
- **Reuse existing collection** — store gate thresholds in `service_trust_levels` collection (DO NOT create a new collection)
- **Reuse TrustLevelService** — call `get_effective_trust_level()` for trust level lookups, don't re-implement
- **Follow HTMX patterns** — server renders HTML, HTMX swaps partials, no client-side JS
- **Permission model** — `@require_role("user")` for reads and evaluate, `@require_role("admin")` for threshold writes
- **Error handling** — Qdrant unreachable should return safe defaults (advisory), not crash
- **Default thresholds** — if no custom thresholds configured in Qdrant, use DEFAULT_GATE_THRESHOLDS in code
- **No Tailwind** — use existing `main.css` BEM classes (`.badge`, `.card`, `.btn`, `.status-indicator`)
- **Test isolation** — mock all Qdrant calls in tests
- **Safe defaults** — missing confidence data → 0.0 score → always advisory
- **Threshold validation** — reject values outside 0.0-1.0 range; reject TL1-2 threshold configuration
- **Service name validation** — reuse the `SERVICE_NAME_PATTERN` regex from trust_config.py for evaluate endpoint

### Project Structure Notes

- All UI route files: `ui/beeper_ui/routes/`
- All service files: `ui/beeper_ui/services/`
- All templates: `ui/beeper_ui/templates/`
- All tests: `ui/tests/`
- Blueprint registration: `ui/beeper_ui/routes/__init__.py`
- Trust level service: `ui/beeper_ui/services/trust_level_service.py` (dependency)
- Trust config routes: `ui/beeper_ui/routes/trust_config.py` (pattern reference)
- Investigation routes: `ui/beeper_ui/routes/investigations.py` (integration point)
- Investigation templates: `ui/beeper_ui/templates/investigations/` (integration point)
- Investigator confidence sources: `investigator/beeper_investigator/steps/rca_hypothesis.py`, `signal_correlation.py`, `resolution_recommendations.py`, `kb_query.py`

### Previous Story Intelligence

**From Story 3-1 (Trust Level Configuration & Persistence):**
- TrustLevelService created with full CRUD for per-service autonomy trust levels
- Uses `service_trust_levels` Qdrant collection with `autonomy_*` prefixed fields
- `TrustLevelConfig` dataclass with `from_qdrant()` classmethod pattern — follow same for ConfidenceGateConfig
- Route pattern: separate API Blueprint (`trust_config_bp`) from UI Blueprint (`trust_settings_bp`)
- Test helper pattern: `_make_autonomy_payload()`, `_make_point()`, `_make_service(mock_client)` — create similar helpers
- **70 tests (31 service + 24 API + 15 UI)** — target similar comprehensive coverage
- Qdrant scroll-based queries for payload-only collections (no vector search needed)
- `SERVICE_NAME_PATTERN` regex compiled at module level for validation

**From Story 3-1 code review fixes:**
- Boolean bypass in validation — ensure threshold validation catches `True`/`False` as invalid floats
- Redundant exception clauses — use `except Exception:` not `except (UnexpectedResponse, Exception):`
- `os.getenv("QDRANT_HOST")` should have `"localhost"` default
- Service name validation with regex + length

### Git Intelligence

Recent commits: `MAESTRO: 3-1 done` → `MAESTRO: implement story 3-1 (Trust Level Configuration & Persistence)`. Current test counts: UI ~1106 passed. Follow commit pattern: `MAESTRO: implement story 3-2 (Confidence Gate Engine)`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.2] — User story, acceptance criteria, BDD scenarios
- [Source: _bmad-output/planning-artifacts/architecture.md#Confidence Gating Strategy] — Default thresholds TL3=90%, TL4=85%, TL5=80%, composite confidence scoring
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust Levels] — TL1-5 definitions and gate behavior
- [Source: _bmad-output/planning-artifacts/architecture.md#API Patterns] — Gate evaluation endpoints under /api/v1/trust/
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Confidence Gates] — Color coding by confidence range, gate display patterns
- [Source: ui/beeper_ui/services/trust_level_service.py] — TrustLevelService dependency, Qdrant collection patterns
- [Source: ui/beeper_ui/routes/trust_config.py] — API Blueprint pattern, RFC 7807 errors, service injection
- [Source: ui/beeper_ui/routes/investigations.py] — Investigation detail routes, confirm/reject endpoints
- [Source: investigator/beeper_investigator/steps/rca_hypothesis.py] — confidence_percentage (0-100), confidence_level text
- [Source: investigator/beeper_investigator/steps/signal_correlation.py] — confidence text levels
- [Source: investigator/beeper_investigator/steps/resolution_recommendations.py] — confidence text per recommendation
- [Source: investigator/beeper_investigator/steps/kb_query.py] — confidence_boost, EXACT_MATCH_THRESHOLD
- [Source: _bmad-output/implementation-artifacts/3-1-trust-level-configuration-persistence.md] — Previous story patterns and learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `ConfidenceGateService` with gate evaluation engine for per-service confidence thresholding
- `GateDecision` dataclass captures full evaluation context: permitted/advisory, score, threshold, trust level, reason
- `ConfidenceGateConfig` dataclass with `from_qdrant()` classmethod for threshold persistence
- Default thresholds: TL3=90%, TL4=85%, TL5=80%; TL1-2 always advisory
- Custom thresholds stored in `service_trust_levels` Qdrant collection using `__gate_thresholds__` sentinel key
- `normalize_confidence_score()` handles mixed investigator formats: RCA percentage, text levels, composite weighting
- `format_gate_message()` produces human-readable gate status messages
- API routes at `/api/v1/trust/gates` with POST evaluate, GET list/single, PUT update (admin-only)
- UI integration: `_confidence_gate.html` HTMX partial in investigation detail with Advisory Only/Auto-action Eligible badges
- Manual Approve button shown when gate blocks at TL3+ (reuses existing confirm endpoint)
- `@require_role("user")` for reads/evaluate, `@require_role("admin")` for threshold writes
- RFC 7807 error responses for validation failures and TL1-2 threshold configuration attempts
- Safe defaults: Qdrant unreachable → use defaults; trust service error → TL1; missing confidence → 0.0
- 64 new tests (43 service + 15 API + 6 UI), all passing
- Full UI suite: 1170 passed (1106 existing + 64 new), zero regressions
- Ruff lint: all clean on new/modified files

### File List

**New files created:**
1. `ui/beeper_ui/services/confidence_gate_service.py` — ConfidenceGateService, GateDecision, ConfidenceGateConfig, normalize_confidence_score, format_gate_message
2. `ui/beeper_ui/routes/confidence_gates.py` — confidence_gates_bp API Blueprint with POST evaluate, GET list/single, PUT update
3. `ui/beeper_ui/templates/investigations/_confidence_gate.html` — HTMX partial for gate status display
4. `ui/tests/test_confidence_gate_service.py` — 43 unit tests for service, normalization, formatting, error handling
5. `ui/tests/test_confidence_gate_routes.py` — 15 API route tests for evaluate, list, get, update
6. `ui/tests/test_confidence_gate_ui.py` — 6 UI integration tests for gate-status endpoint

**Files modified:**
1. `ui/beeper_ui/routes/__init__.py` — Register confidence_gates_bp
2. `ui/beeper_ui/routes/investigations.py` — Add gate-status route, import confidence gate service
3. `ui/beeper_ui/templates/investigations/_detail_content.html` — Include confidence gate card in investigation detail
