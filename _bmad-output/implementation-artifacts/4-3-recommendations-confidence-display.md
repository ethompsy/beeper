# Story 4.3: Recommendations & Confidence Display

Status: done

## Story

As an **SRE**,
I want to view recommended resolutions with confidence levels,
so that I understand how certain Beeper is about its findings and can make informed resolution decisions.

## Acceptance Criteria

1. **Given** an investigation has generated recommendations, **When** I view the investigation, **Then** I see recommendations with confidence levels (FR33) **And** confidence is displayed as: High (>80%), Medium (50-80%), Low (<50%).

2. **Given** recommendations are displayed, **When** I view them, **Then** each recommendation shows: action to take, confidence level with visual indicator, supporting evidence summary (expected outcome), risk assessment.

3. **Given** multiple recommendations exist, **When** I view the list, **Then** they are ranked by confidence **And** the top recommendation is highlighted.

4. **Given** confidence is low, **When** I view recommendations, **Then** a warning indicates uncertainty **And** alternative hypotheses are shown **And** "Gather more information" options are suggested (diagnostic_actions).

## Tasks / Subtasks

- [x] Task 1: Create `_recommendations.html` template partial (AC: 1, 2, 3, 4)
  - [x] 1.1 Create `ui/beeper_ui/templates/investigations/_recommendations.html` — renders the full recommendations section from `findings` dict data
  - [x] 1.2 Iterate over `findings.get('recommendations', [])` — each recommendation is a dict with keys: `action`, `confidence`, `expected_outcome`, `risk_assessment`, `based_on_prior_incident`
  - [x] 1.3 Render each recommendation as a `.recommendation-card` with: action text, confidence badge (`.confidence-badge.confidence-{level}`), risk badge (`.risk-badge.risk-{level}`), expected outcome paragraph, prior incident link (if `based_on_prior_incident` is not None)
  - [x] 1.4 Highlight the first recommendation (index 0) with `.recommendation-top` class — recommendations are pre-sorted by confidence desc, risk asc from the pipeline
  - [x] 1.5 Display `findings.get('ranking_rationale', '')` below the recommendation list as `.ranking-rationale` text
  - [x] 1.6 Add low-confidence warning section: **When** any recommendation has `confidence == "low"` OR `findings.get('synthesis_source') == "fallback"`, show `.low-confidence-warning` banner with message "Low confidence — recommendations may need validation"
  - [x] 1.7 Render `findings.get('diagnostic_actions', [])` as a `.diagnostic-actions` checklist when present — these are safe investigative steps the SRE can take before acting on recommendations
  - [x] 1.8 Display alternative hypotheses from RCA data: `findings.get('alternative_hypotheses', [])` in a collapsible `<details>` section when low confidence, reusing existing `.alternative-hypothesis` CSS class from 4-2
  - [x] 1.9 Handle empty state: when `findings.get('recommendations')` is None or empty list, show "No recommendations yet — investigation still in progress" message
  - [x] 1.10 Add `synthesis_source` indicator: show "AI-generated" badge when `synthesis_source == "llm"`, "Fallback" badge when `synthesis_source == "fallback"`

- [x] Task 2: Update `_findings.html` to use new recommendations partial (AC: 1, 2, 3)
  - [x] 2.1 Replace the existing simple "Resolution Recommendation" `<div class="findings-section">` block in `_findings.html` with `{% include "investigations/_recommendations.html" %}` — the `findings` dict is already in template context
  - [x] 2.2 Ensure the recommendations section is visually distinct from other findings sections — use a `.findings-section.recommendations-section` wrapper with enhanced visual treatment (slightly different border/background to draw attention)
  - [x] 2.3 Move recommendations section to be the LAST findings section (after RCA hypothesis) so it appears as the conclusion/actionable outcome of the investigation

- [x] Task 3: Add CSS styles for recommendation cards (AC: 1, 2, 3, 4)
  - [x] 3.1 Add `.recommendation-card` styles to `static/css/main.css`: card layout with left border color-coded by confidence level (green=high, yellow=medium, red=low), padding, margin-bottom for spacing between cards
  - [x] 3.2 Add `.recommendation-top` styles: slightly larger card, subtle highlight background (`#f0fdf4` green-tint for high confidence, `#fffbeb` yellow-tint for medium, `#fef2f2` red-tint for low), "Top Recommendation" label badge
  - [x] 3.3 Add `.confidence-badge` inline badge styles: `.confidence-badge.confidence-high` (green `#22c55e` bg), `.confidence-badge.confidence-medium` (yellow `#eab308` bg), `.confidence-badge.confidence-low` (red `#ef4444` bg) — follow existing `.impact-badge` sizing pattern
  - [x] 3.4 Add `.risk-badge` inline badge styles: `.risk-badge.risk-high` (red `#fee2e2` bg, `#991b1b` text), `.risk-badge.risk-medium` (yellow `#fef3c7` bg, `#92400e` text), `.risk-badge.risk-low` (green `#dcfce7` bg, `#166534` text) — follow existing badge pattern
  - [x] 3.5 Add `.low-confidence-warning` banner: yellow background (`#fef3c7`), amber border, warning icon via CSS, padding, margin-bottom
  - [x] 3.6 Add `.diagnostic-actions` list styles: ordered list with checkbox-like indicators, muted text color, indented under warning banner
  - [x] 3.7 Add `.ranking-rationale` styles: italic text, muted color (`#6b7280`), smaller font, top border separator
  - [x] 3.8 Add `.synthesis-badge` styles: small pill badge, `.synthesis-llm` (blue tint), `.synthesis-fallback` (gray tint)
  - [x] 3.9 Add `.prior-incident-link` styles: inline link with icon indicator, underline on hover
  - [x] 3.10 Add `.recommendations-section` wrapper: slightly different from standard `.findings-section` — subtle accent border or background to distinguish actionable recommendations from analytical findings

- [x] Task 4: Route and SSE integration verification (AC: 1, 2, 3)
  - [x] 4.1 Verify the existing `investigation_detail()` route in `investigations.py` passes `findings` dict to template context — no route changes needed since `get_investigation_findings()` already returns all pipeline metadata including recommendations data
  - [x] 4.2 Verify the existing `findings-update` SSE event in `investigation_detail_stream()` re-renders `_findings.html` (which now includes `_recommendations.html`) — no SSE changes needed
  - [x] 4.3 If the pipeline metadata keys differ from expected (e.g., `resolution_recommendation` singular vs `recommendations` list), add a data normalization helper in the route that transforms findings data before passing to template — check actual Qdrant data against `resolution_recommendations.py` StepResult.data keys

- [x] Task 5: Tests for recommendations display (AC: 1, 2, 3, 4)
  - [x] 5.1 Test `GET /investigations/<id>` renders recommendation cards when findings contain `recommendations` list — verify each card shows action, confidence badge, risk badge, expected outcome
  - [x] 5.2 Test top recommendation is highlighted with `.recommendation-top` class
  - [x] 5.3 Test ranking rationale text is displayed
  - [x] 5.4 Test low confidence warning appears when any recommendation has `confidence == "low"`
  - [x] 5.5 Test diagnostic actions list renders when present in findings
  - [x] 5.6 Test alternative hypotheses display when low confidence (from RCA data in same findings dict)
  - [x] 5.7 Test empty recommendations state — "No recommendations yet" message when `recommendations` key missing or empty
  - [x] 5.8 Test fallback source indicator when `synthesis_source == "fallback"`
  - [x] 5.9 Test prior incident link renders when `based_on_prior_incident` is not None
  - [x] 5.10 Test HTMX partial response (with `HX-Request` header) includes recommendations HTML
  - [x] 5.11 Test SSE `findings-update` event includes recommendation cards in rendered HTML

- [x] Task 6: Integration verification (AC: 1, 2, 3, 4)
  - [x] 6.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [x] 6.2 Run `mypy --strict` on all new/modified Python files — fix any issues
  - [x] 6.3 Run full Python test suite — verify zero regressions
  - [x] 6.4 Verify recommendations display renders correctly within investigation detail page (manual template inspection)

## Dev Notes

### Architecture Decision: Template-Only Enhancement

Story 4-3 is primarily a **template and CSS enhancement** — no new API endpoints, service methods, or SSE events are needed. The data pipeline is already complete:

1. `ResolutionRecommendationStep` in `investigator/beeper_investigator/steps/resolution_recommendations.py` generates recommendations and stores them in `StepResult.data`
2. The agent pipeline stores step results in Qdrant `investigations` collection as pipeline metadata
3. `InvestigationService.get_investigation_findings()` retrieves the metadata as a flat dict
4. The investigation detail route passes this dict as `findings` to templates
5. The existing `findings-update` SSE event re-renders `_findings.html` when new data arrives

**What changes:** Only the template rendering and CSS — replace the basic text display with rich recommendation cards.

### Critical Data Schema: ResolutionRecommendationStep Output

The `StepResult.data` dict from `resolution_recommendations.py` (lines 393-405) contains:

```python
{
    "recommendations": [                    # list of recommendation dicts
        {
            "action": "specific action description",           # str
            "confidence": "high" | "medium" | "low",          # str
            "expected_outcome": "what happens if action taken", # str
            "risk_assessment": "high" | "medium" | "low",     # str
            "based_on_prior_incident": "incident-id" | None,  # str | None
        },
        # ... up to 5 recommendations, sorted by confidence desc then risk asc
    ],
    "recommendation_count": 3,              # int
    "ranking_rationale": "why ordered this way",  # str
    "diagnostic_actions": [                 # list[str] — safe diagnostic steps
        "Check service logs for error patterns",
        "Verify recent deployments or config changes",
    ],
    "synthesis_source": "llm" | "fallback", # str — how recommendations were generated
    "resolution_model_tier": "standard",    # str
    "resolution_model_used": "model-name",  # str | None
}
```

**Template access pattern:** `findings.get('recommendations', [])`, `findings.get('ranking_rationale', '')`, etc.

**IMPORTANT DATA KEY NOTE:** The 4-2 dev notes table listed simplified keys (`resolution_recommendation`, `estimated_mttr_minutes`, etc.) which may differ from the actual StepResult.data keys above. The **source of truth is `resolution_recommendations.py`** lines 393-405. If the existing `_findings.html` uses the simplified keys, Task 4.3 addresses this by adding normalization.

### Confidence Level Bands

| Level | Percentage Range | Color | Meaning |
|-------|-----------------|-------|---------|
| high | >80% | Green (`#22c55e`) | Proven fix, confirmed by evidence or prior incident |
| medium | 50-80% | Yellow (`#eab308`) | Likely effective based on RCA but not confirmed |
| low | <50% | Red (`#ef4444`) | Speculative, needs validation before acting |

Note: Individual recommendations have a `confidence` field (high/medium/low enum), while the RCA hypothesis has both `confidence_level` and `confidence_percentage` (numeric). The confidence badges on recommendation cards use the per-recommendation `confidence` field, NOT the RCA percentage.

### Existing Patterns to Reuse

- **Confidence indicator CSS:** Already exists from 4-2 for RCA hypothesis (`.confidence-indicator`, `.confidence-bar`, `.confidence-high/medium/low`) — reuse color palette but create new `.confidence-badge` for inline card badges
- **Badge patterns:** `.impact-badge`, `.match-badge`, `.escalation-badge`, `.mttr-estimate` in `main.css` — follow same sizing/padding/font patterns for new `.risk-badge` and `.confidence-badge`
- **Alternative hypotheses:** `.alternative-hypotheses`, `.alternative-hypothesis` CSS classes from 4-2 — reuse directly for AC4 display
- **Expandable sections:** `<details>`/`<summary>` pattern from `_evidence_panel.html` — reuse for alternative hypotheses in low-confidence state
- **Template includes:** `{% include "investigations/_partial.html" %}` pattern from `_findings.html`/`_detail_content.html`
- **Safe dict access:** `findings.get('key', default)` pattern throughout existing templates

### Anti-Patterns to Avoid

- **DO NOT** create new service methods — `get_investigation_findings()` already returns all needed data
- **DO NOT** create new SSE events — `findings-update` already re-renders the findings section
- **DO NOT** create new API endpoints — recommendations data is in Qdrant pipeline metadata
- **DO NOT** create new JavaScript — HTMX handles all dynamic behavior
- **DO NOT** create new CSS files — add to existing `main.css`
- **DO NOT** duplicate confidence indicator styles — reuse color palette from 4-2, create minimal new badge classes
- **DO NOT** hardcode recommendation data — always use `findings.get()` with defaults for resilience
- **DO NOT** render raw HTML from recommendation action text — use Jinja2 autoescaping (default)

### Key File Paths

| Component | Path | Action |
|-----------|------|--------|
| Recommendations template (NEW) | `ui/beeper_ui/templates/investigations/_recommendations.html` | Create |
| Findings template (modify) | `ui/beeper_ui/templates/investigations/_findings.html` | Replace resolution section with include |
| CSS styles (modify) | `ui/beeper_ui/static/css/main.css` | Add recommendation card styles |
| Investigation routes (verify) | `ui/beeper_ui/routes/investigations.py` | Verify data flow, possible normalization helper |
| Route tests (modify) | `ui/tests/test_investigation_routes.py` | Add recommendation rendering tests |
| Resolution step (reference only) | `investigator/beeper_investigator/steps/resolution_recommendations.py` | Data schema source of truth |

### Testing Standards

- **pytest** with Flask test client for route tests
- **respx** for mocking operator HTTP calls
- **MagicMock** for Qdrant client in findings tests
- Mock findings dict with full recommendations data structure matching `resolution_recommendations.py` output
- Test both full page (`GET /investigations/<id>`) and HTMX partial (`HX-Request: true`) responses
- Test edge cases: empty recommendations, single recommendation, fallback source, low confidence
- `ruff check` and `mypy --strict` on all modified Python files

### Previous Story Intelligence (from 4-2)

**Patterns established:**
- Investigation detail page loads findings from Qdrant via `get_investigation_findings()`
- Findings dict is passed directly to templates as `findings` context variable
- SSE `findings-update` event re-renders `_findings.html` with latest findings data
- All CSS in `main.css` using BEM-like naming (`.findings-section`, `.hypothesis-card`, etc.)
- 4-2 code review fixed: SSE generator resource leak (add `svc.close()`), CSS injection risk (use `|int` filter for percentages), Qdrant client leak (close in service `close()`)

**Lessons learned:**
- Always use `stream_with_context` for SSE generators
- Sanitize all template outputs — use `|int`, `|e` filters where needed
- Test SSE event content, not just content type
- Close all clients (httpx + Qdrant) in service `close()` method

### Project Structure Notes

- New template `_recommendations.html` follows existing partial naming convention (`_` prefix) in `templates/investigations/`
- No new Python modules, routes, or services needed — purely template + CSS enhancement
- No new dependencies required
- All changes within `ui/` directory except reference to `investigator/` for data schema

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.3]
- [Source: investigator/beeper_investigator/steps/resolution_recommendations.py — StepResult data schema, lines 393-405]
- [Source: investigator/beeper_investigator/steps/__init__.py — StepResult dataclass]
- [Source: ui/beeper_ui/templates/investigations/_findings.html — current resolution display to replace]
- [Source: ui/beeper_ui/routes/investigations.py — investigation_detail route, SSE streaming]
- [Source: ui/beeper_ui/services/investigation_service.py — get_investigation_findings()]
- [Source: ui/beeper_ui/static/css/main.css — existing badge/confidence styles]
- [Source: _bmad-output/implementation-artifacts/4-2-real-time-investigation-pane.md — previous story patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Template-only enhancement — no new endpoints, services, or SSE events needed
- Data schema source of truth: resolution_recommendations.py StepResult.data (lines 393-405)
- Key data keys: recommendations (list), ranking_rationale, diagnostic_actions, synthesis_source
- Confidence bands: high >80% green, medium 50-80% yellow, low <50% red
- 6 tasks: new template partial, update findings template, CSS styles, route verification, tests, integration
- Reuse existing badge/confidence CSS patterns from 4-2 for consistency
- Previous story 4-2 review fixes inform testing approach (SSE resource cleanup, CSS injection prevention, Qdrant client management)

### Change Log

- 2026-03-06: Implemented story 4-3 — template-only enhancement with rich recommendation cards, confidence badges, risk badges, diagnostic actions, alternative hypotheses, and comprehensive CSS. 11 new tests added, 341 total pass, zero regressions. Ruff + mypy clean on all modified files.
- 2026-03-06: Code review found 7 issues (1 HIGH, 4 MEDIUM, 2 LOW). Fixed: (1) duplicate alternative hypotheses — replaced duplicate list in recommendations with reference to RCA section, (2) prior incident link URL-encoded with `|urlencode` filter, (3) defensive `{% if rec is mapping %}` guard on recommendation iteration, (4) yellow confidence badge contrast fixed (white → dark brown `#78350f`), (5) missing negative test added — `test_no_warning_when_all_high_confidence`, (6) recommendations section conditionally rendered when data exists, (7) `role="alert"` on low-confidence warning banner. Added 3 new tests (14 total), 344 total pass, zero regressions. Ruff + mypy clean. Sprint status + story → done.

### File List

- `ui/beeper_ui/templates/investigations/_recommendations.html` (NEW) — Recommendations partial template with confidence badges, risk badges, diagnostic actions, alternative hypotheses, synthesis source indicators
- `ui/beeper_ui/templates/investigations/_findings.html` (MODIFIED) — Replaced simple resolution text with `{% include "_recommendations.html" %}`, added `.recommendations-section` wrapper
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — Added ~200 lines of CSS: recommendation cards, confidence/risk badges, low-confidence warning, diagnostic actions, ranking rationale, synthesis badges, prior incident links
- `ui/tests/test_investigation_routes.py` (MODIFIED) — Added 11 new tests in `TestRecommendationsDisplay` class covering all ACs
- `_bmad-output/implementation-artifacts/4-3-recommendations-confidence-display.md` (MODIFIED) — Story status → review, all tasks marked complete
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED) — 4-3 status → in-progress
