# Route Parity Targets — Milestone 2.1 (Remaining Route Migration)

**Status: FULL (Task 5.0).** Confirms the live route inventory and pins a written parity target for every route Milestone 2.1 (Tasks 5.1–5.4) will migrate, per FR50/NFR20 ("each React view reaches parity with the Jinja view it replaces"). This closes the "parity with what?" gap Task 5.0 exists to close (`docs/plans/react-ui.md` Milestone 2.1).

**Scope:** every sidebar nav destination declared in `ui/beeper_ui/templates/components/layout.html` (16 items across Observe/Learn/Manage), plus the sub-routes each one dual-mode-serves. Tasks 5.1–5.4 get a full target row each; the remaining nav routes are recorded as **later increment, target pinned** so nothing is left ambiguous — a future task can pick any of them up without re-deriving this inventory.

**How this doc is verified:** `ui/tests/test_route_parity_targets.py` parses this file and asserts (1) every route block below has a non-empty parity target that resolves to a real `templates/<name>.html` file and/or a well-formed FR id that appears in `docs/reqs/main.md`, and (2) every sidebar nav destination discovered by parsing `layout.html` is covered by a block here. See that file for the exact assertions; a future nav addition that isn't added to this doc fails CI instead of silently going untracked.

---

## How to read a route block

Each block is one migration unit (one task, or one "later increment" nav destination) with a fixed set of `- **Field:**` lines so the guard test can parse it mechanically:

- **Jinja URL(s):** the live Flask/Jinja route(s) this unit covers today (full-page and HTMX-partial variants).
- **React URL (canonical, dev-time, under `/app`):** the URL Tasks 5.1–5.4 should build and test against right now. React Router's `basename` is `/app` (`ui/frontend/src/App.tsx`) and Vite's asset `base` is `/app/` (`ui/frontend/vite.config.ts`), so every built asset and route match is anchored there today — this is the URL that actually works with the current router config.
- **REACT_OWNED_PREFIXES value (future cutover):** the bare Jinja-path prefix that will eventually be appended to `REACT_OWNED_PREFIXES` (`ui/beeper_ui/routes/react_registry.py`) so the *existing* Jinja URL — not `/app/...` — transparently starts serving the React shell. **Not changed by this task** (constraint: "do NOT change `REACT_OWNED_PREFIXES`"). See the "known gap" note below — this cutover is not yet wired end-to-end.
- **Parity target:** the FR id(s) (must appear in `docs/reqs/main.md`) and/or the exact `templates/<name>.html` path(s) (must exist on disk) that define "done." Where no FR covers the route, that is stated explicitly and the template is the sole target — never an invented FR id.
- **Dual-mode/HTMX:** whether the Jinja route returns a full page or an `HX-Request` partial, and whether the React target must replace both response modes or only the full page (the React SPA has no server-rendered partial-swap equivalent — HTMX partials are superseded by client-side state/fetch, not carried over 1:1).
- **Permalink state to URL-encode:** per FR53, which query/path state must round-trip through the URL. "None" if the view has no addressable filter state.
- **Data source:** the Flask blueprint + service module the route reads from.
- **Scope / carve-outs:** what's explicitly excluded from the pinned task.

---

## 1. Already migrated (Phase 1) — reference only, not Task 5.0/5.1–5.4 scope

### Investigations — list + detail

- **Nav label:** Investigations (Observe)
- **Jinja URL(s):** `/investigations/` (list, `investigations/list.html` / HTMX partial `investigations/_list_content.html`); `/investigations/<id>` (detail, `investigations/detail.html` / `investigations/_detail_content.html`)
- **React URL (canonical, dev-time, under `/app`):** `/app/investigations`, `/app/investigations/<investigationId>`
- **REACT_OWNED_PREFIXES value (future cutover):** `/investigations`
- **Parity target:** FR22, FR23, FR24, FR25, FR26, FR27, FR41–FR44, FR45–FR47, FR49, FR53 · `templates/investigations/list.html`, `templates/investigations/detail.html`
- **RETIRED (Task 6.3, 2026-08-08):** the two templates cited above no longer exist — `/investigations/` and `/investigations/<id>` now 302-redirect to `/app/investigations`/`/app/investigations/<id>` (D14) and their Jinja render path was removed. `templates/investigations/_list_content.html`, `_detail_content.html`, `_filter_panel.html`, `_detail_not_found.html` were also removed (partials solely used by the two deleted pages). The many per-investigation HTMX action routes (verify/confirm/reject/resolve/feedback/related-kb/linked-kb/gate-status/urgency/remediation-progress) and the per-investigation HTML SSE stream are explicitly NOT part of this retirement — they were never called by React and remain Jinja-rendered; see `ui/beeper_ui/routes/react_registry.py`'s `_REDIRECT_EXCLUSION_PATTERNS` and the Task 6.3 report for the full reasoning.
- **Dual-mode/HTMX:** both modes replaced — `InvestigationListPage`/`InvestigationDetailPage` (`ui/frontend/src/routes/`) consume the REST + SSE API directly; no HTMX partial equivalent needed.
- **Permalink state to URL-encode:** status-group filter (list); investigation id + anchored step `#step-<id>` (detail).
- **Data source:** `investigations_bp` (`ui/beeper_ui/routes/investigations.py`) / operator REST + SSE API directly from the frontend.
- **Scope / carve-outs:** shipped in Milestones 1.1–1.3. Listed here for completeness only — Task 5.0 does not re-pin this target, it is already implemented and tested.

---

## 2. Task 5.1 — Knowledge Base browse/search + entry detail

- **Nav label:** Knowledge Base (Learn)
- **Jinja URL(s):** `/knowledge/` (browse, `knowledge/index.html`); `/knowledge/search` (search, HTMX-only partial `knowledge/_search_results.html` — no full-page equivalent, this route is `hx-get`-only); `/knowledge/<entry_id>` (detail, `knowledge/entry.html`)
- **React URL (canonical, dev-time, under `/app`):** `/app/knowledge`, `/app/knowledge/search?q=<query>`, `/app/knowledge/<entryId>`
- **REACT_OWNED_PREFIXES value (future cutover):** `/knowledge`
- **Parity target:** FR28, FR29, FR31, FR53 · `templates/knowledge/index.html`, `templates/knowledge/_search_results.html`, `templates/knowledge/entry.html`
- **RETIRED (Task 6.3, 2026-08-08):** the three templates cited above no longer exist — `/knowledge/`, `/knowledge/search`, and `/knowledge/<entry_id>` now 302-redirect to `/app/knowledge` (D14; search collapses into the same view via its `?q=` permalink, not a separate `/app/knowledge/search` route) and their Jinja render path was removed. `templates/knowledge/_entry_list.html`, `_filter_panel.html`, `_active_filters.html` were also removed (partials solely used by the retired pages). Every carve-out listed below remains Jinja-rendered exactly as before — confirmed still excluded from the redirect by `react_registry.py`'s `_REDIRECT_EXCLUSION_PATTERNS`.
- **Dual-mode/HTMX:** `/knowledge/` is full-page only (no `HX-Request` branch in `kb_index`). `/knowledge/search` is HTMX-partial only — it is never requested as a full page in the Jinja app (search lives inside `/knowledge/`'s page shell and swaps `#search-results` via HTMX). The React target replaces this with a client-side search view — no partial-swap needed, just a fetch-and-render on the `/app/knowledge/search` route (or query param on `/app/knowledge`, implementer's call, as long as `q` is URL-encoded per FR53). `/knowledge/<entry_id>` is full-page only.
- **Permalink state to URL-encode:** `q` (search keyword) is the FR53/FR29-required minimum. `entry_type`, `service`, `date_range` are additional Jinja filters (`kb_search`, `ui/beeper_ui/routes/knowledge.py:406-425`) — encode them too if carried into the React search UI; not carrying them is not a parity regression since FR53 only names the query.
- **Data source:** `knowledge_bp` (`ui/beeper_ui/routes/knowledge.py`) / `KBService` (`ui/beeper_ui/services/kb_service.py`), `EmbeddingService` (`ui/beeper_ui/services/embedding_service.py`) for semantic search.
- **Scope / carve-outs:** `/knowledge/import`, `/knowledge/<id>/edit`, `/knowledge/<id>/history`, `/knowledge/<id>/version/<n>`, `/knowledge/<id>/diff/<from>/<to>`, `/knowledge/<id>/restore/<n>`, `/knowledge/<id>/corrections*`, `/knowledge/learning*`, `/knowledge/trust-settings`, `/knowledge/services/<name>/knowledge` remain Jinja-only — out of Task 5.1's browse+search+detail scope, not pinned by this task, and not blocking 5.1's `[T]` AC.

---

## 3. Task 5.2 — Ingestion/Detection Stats

- **Nav label:** Ingestion Stats (Observe)
- **Jinja URL(s):** `/health/ingestion` (`health/ingestion.html` / HTMX partial `health/_ingestion_content.html`)
- **React URL (canonical, dev-time, under `/app`):** `/app/ingestion-stats`
- **REACT_OWNED_PREFIXES value (future cutover):** `/health/ingestion`
- **Parity target:** FR32, FR33 · `templates/health/ingestion.html`
- **RETIRED (Task 6.3, 2026-08-08):** the template cited above no longer exists — `/health/ingestion` now 302-redirects to `/app/ingestion-stats` (D14, a target-override rewrite since the React route name differs from the Jinja path) and its Jinja render path was removed. `templates/health/_ingestion_content.html` was also removed. `/health/` (§7) and `/health/api` are untouched, separate routes.
- **Dual-mode/HTMX:** both modes collapse into one React view — the Jinja route's `HX-Request` branch exists only to power `hx-trigger="every 5s"` auto-refresh (`health/ingestion.html`, `ui/beeper_ui/routes/health.py:106-138`); the React target must replace the *auto-refresh behavior* (poll or SSE, implementer's call) but has no separate partial route to build — one component, client-side refetch.
- **Permalink state to URL-encode:** none — this view has no user-set filter/selection state, only live counters.
- **Data source:** `health_bp` (`ui/beeper_ui/routes/health.py`) / `HealthService.get_ingestion_stats()` (`ui/beeper_ui/services/health_service.py`).
- **Scope / carve-outs:** `/health/` (the general operator-health overview, distinct route — see §7 below) is explicitly NOT this task's target, even though it also renders `ingestion_stats` as one optional field among several components. Task 5.2 targets `/health/ingestion` only.
- **Note — existing React href mismatch (do not silently fix):** `ui/frontend/src/routes/AppLayout.tsx` `NAV_GROUPS` currently has `{ id: 'ingestion-stats', label: 'Ingestion Stats', href: '/ingestion-stats' }` — missing the leading `/health` segment present in the Jinja URL and in the canonical dev-time URL pinned above (`/app/ingestion-stats` is fine as the *React Router path*, since it's a client-side route id, not required to mirror the Jinja path 1:1 — but flagging here because the discrepancy could be mistaken for a bug by whoever builds 5.2. It isn't one: `href` values in `AppLayout.tsx` are React Router paths under `/app`, not required to equal the Jinja URL. What *would* be a bug is if 5.2 assumes `/app/ingestion-stats` already routes correctly — it doesn't yet; `App.tsx`'s router has no `ingestion-stats` route registered, only `investigations` and `investigations/:id`. Task 5.2 must add the route.)

---

## 4. Task 5.3 — Sources + LLM Spending

### 4a. Sources

- **Nav label:** Sources (Observe)
- **Jinja URL(s):** `/sources/` (`sources/list.html` / HTMX partial `sources/_list_content.html`)
- **React URL (canonical, dev-time, under `/app`):** `/app/sources`
- **REACT_OWNED_PREFIXES value (future cutover):** `/sources`
- **Parity target:** FR34 · `templates/sources/list.html`
- **RETIRED (Task 6.3, 2026-08-08):** the template cited above no longer exists — `/sources/` now 302-redirects to `/app/sources` (D14) and its Jinja render path was removed. `templates/sources/_list_content.html` was also removed.
- **Dual-mode/HTMX:** collapses into one React view — the `HX-Request` branch exists only to power `hx-trigger="every 5s"` auto-refresh (`sources/list.html:12`, `ui/beeper_ui/routes/sources.py:18-44`); same treatment as Ingestion Stats (§3).
- **Permalink state to URL-encode:** none.
- **Data source:** `sources_bp` (`ui/beeper_ui/routes/sources.py`) / `SourceService.get_sources()` (`ui/beeper_ui/services/source_service.py`).
- **Scope / carve-outs:** none — `/sources/` is the entire nav destination.

### 4b. LLM Spending

- **Nav label:** Spending (Manage)
- **Jinja URL(s):** `/spending/` (`spending/spending.html` / HTMX partial `spending/_spending_content.html`); `/spending/status` (HTMX-only partial, powers `hx-trigger="every 30s"` — no full-page equivalent)
- **React URL (canonical, dev-time, under `/app`):** `/app/spending`
- **REACT_OWNED_PREFIXES value (future cutover):** `/spending`
- **Parity target:** FR35 · `templates/spending/spending.html`
- **RETIRED (Task 6.3, 2026-08-08):** the template cited above no longer exists — `/spending/` and `/spending/status` now 302-redirect to `/app/spending` (D14; `status` collapses into the same view via a target-override rewrite, it never had a page of its own) and their Jinja render path was removed. `templates/spending/_spending_content.html` was also removed. Cost Insights (`/spending/costs*`, §7) is untouched — confirmed excluded from the redirect by `react_registry.py`'s `_REDIRECT_EXCLUSION_PATTERNS`.
- **Dual-mode/HTMX:** collapses into one React view; `/spending/status` is the auto-refresh partial (30s interval, `spending/spending.html:12`) — same treatment as §3/4a, no separate route needed client-side.
- **Permalink state to URL-encode:** none — the dashboard has no user-set filter/selection state (that's Cost Insights, `/spending/costs`, which is a separate nav destination — see §7).
- **Data source:** `spending_bp` (`ui/beeper_ui/routes/spending.py`) / `SpendingService` (`ui/beeper_ui/services/spending_service.py`).
- **Scope / carve-outs:** `/spending/costs`, `/spending/costs/breakdown`, `/spending/costs/export` are the separate **Cost Insights** nav destination (§7) — not part of Task 5.3.

---

## 5. Task 5.4 — Metrics (MTTR dashboard)

**This is the explicit "parity with what?" gap Task 5.0 exists to close.** Resolution:

- **Nav label:** Metrics (Learn)
- **Jinja URL(s):** `/metrics/` (`metrics/mttr.html` / HTMX partial `metrics/_mttr_content.html`); `/metrics/mttr` (same content, alternate route — `ui/beeper_ui/routes/metrics.py:182`); `/metrics/mttr/drilldown` (HTMX partial, `metrics/_drilldown.html`); `/metrics/export` (CSV/JSON download, no template)
- **React URL (canonical, dev-time, under `/app`):** `/app/metrics`
- **REACT_OWNED_PREFIXES value (future cutover):** `/metrics`
- **Parity target:** `templates/metrics/mttr.html` (no FR id)
- **RETIRED (Task 6.3, 2026-08-08):** the template cited above no longer exists — `/metrics/`, `/metrics/mttr`, and `/metrics/mttr/drilldown` now 302-redirect to `/app/metrics` (D14; the mttr/drilldown variants are target-override rewrites to the same view, drilldown state deliberately isn't a URL permalink) and their Jinja render path was removed. `templates/metrics/_mttr_content.html`, `_drilldown.html` were also removed. `/metrics/export` (CSV/JSON, no template) is untouched — confirmed excluded from the redirect.
- **Parity target rationale:** `/metrics/` renders the **MTTR (Mean Time To Resolution) Trends Dashboard** — period/service/severity-filtered MTTR trend charts and drilldowns, sourced from `MetricsService` (`ui/beeper_ui/services/metrics_service.py`). Checked against the requirements doc's full functional-requirement list: no functional requirement names MTTR reporting, trend charts, or a metrics dashboard. The Spending FR covers LLM cost tracking (§4b), not MTTR; the ingestion/detection-stats FRs cover pipeline throughput and anomaly counters (§3), not MTTR. There is no FR to cite — **the template is the sole, complete parity target**, per this doc's own rule (never invent an FR id to fill the gap).
- **Dual-mode/HTMX:** `/metrics/` and `/metrics/mttr` both collapse into one React view (period/service/severity filters currently re-fetch `_mttr_content.html` via HTMX `hx-get`; the React target re-fetches client-side instead). `/metrics/mttr/drilldown` is a service-level detail sub-view — the React target should reproduce it as a nested route or expandable section, implementer's call, as long as its content (per-service MTTR breakdown) is reachable from `/app/metrics`. `/metrics/export` (CSV/JSON) has no template to target — parity here means "an equivalent export affordance exists," verified functionally, not against a template.
- **Permalink state to URL-encode:** `period` (week/month/quarter), `service`, `severity` — these are real `<select>`-driven HTMX filters (`metrics/mttr.html:22-52`) with a backing query (`MetricsService` accepts all three), so per FR53's "every encoded state must have a backing reload path" rule they are permalink-eligible and should be encoded, even though FR53's own enumerated list (Investigation list/detail, KB search) doesn't explicitly name Metrics — FR53's rule is general ("every migrated view is a shareable permalink"), the per-surface bullets are the two first-increment surfaces plus KB, not an exhaustive closed list. Task 5.4 should treat this as good practice, not a hard `[T]` blocker, since no FR/task AC currently names it as such.
- **Data source:** `metrics_bp` (`ui/beeper_ui/routes/metrics.py`) / `MetricsService` (`ui/beeper_ui/services/metrics_service.py`).
- **Scope / carve-outs:** none beyond the sub-routes already enumerated above.

---

## 6. Known parity gaps / deliberate non-targets

These are pre-existing findings surfaced during this inventory pass. They are recorded, not fixed — fixing any of them is out of Task 5.0's scope (documentation + guard-test only).

1. **`AppLayout.tsx` `NAV_GROUPS` is incomplete.** It declares 6 nav items (`investigations`, `sources`, `ingestion-stats`, `knowledge-base`, `metrics`, `spending`) vs. Jinja's 16. This is expected — Phase 1 only needed placeholders for the routes it shipped. Tasks 5.1–5.4 will need to extend `NAV_GROUPS` (and `App.tsx`'s router) as they land; this doc's canonical React URLs (§2–§5) are what those additions should use.
2. **Two existing `href` mismatches in `AppLayout.tsx`, as of this pass:**
   - `Ingestion Stats → /ingestion-stats` (missing the `/health` segment the Jinja URL has). Not itself a bug — `href` is a client-side React Router path, not required to mirror the Jinja URL — but no route is registered for it yet in `App.tsx`; Task 5.2 must add one. See §3's note for the full explanation of why this isn't silently "fixed" here.
   - `Knowledge Base → /knowledge-base` (vs. Jinja `/knowledge/`; canonical React URL pinned in §2 is `/app/knowledge`, not `/app/knowledge-base`). Task 5.1 should register its route at `knowledge`, not `knowledge-base`, and update `AppLayout.tsx`'s `href` to match when it lands, so the sidebar link isn't dead.
   Neither is fixed by this task — Task 5.0's constraints explicitly forbid touching React source beyond reading it. Flagging so 5.1/5.2 don't propagate the mismatch or invent a third convention.
3. **`activeItemId="investigations"` is hardcoded in `AppLayout.tsx`** rather than derived from the current route. Every migrated view currently renders with "Investigations" highlighted in the sidebar regardless of the actual active route. Tasks 5.1–5.4 will make this visibly wrong (e.g. viewing `/app/knowledge` with "Investigations" highlighted) unless whichever task lands first also fixes route-derived active-item computation. Not assigned to any specific task by this doc — flagging as a cross-cutting concern the first of 5.1–5.4 to land should pick up, or escalate back to the orchestrator as a shared prerequisite.
4. **Jinja's own active-nav highlighting is already inconsistent, and this is a deliberate *non*-target.** Of all Jinja page routes, only `health/ingestion.html:6` sets `{% block active_item %}` (`/health/ingestion`); every other page (including `/investigations/`, `/knowledge/`, `/spending/`, etc.) renders with no active-nav highlight at all — `active_item` defaults to `''` in `components/layout.html`'s `layout_shell` macro, and no other template overrides it. **React should derive active state correctly from the route (see finding 3), not replicate this bug** — parity means matching Jinja's *content and capability*, not its incidental sidebar-highlighting defect.
5. **`REACT_OWNED_PREFIXES` cutover mechanism is not yet exercised end-to-end for non-`/app` URLs.** `serve_react_shell` (`ui/beeper_ui/routes/react_shell.py`) always serves `dist/index.html` verbatim, and that `index.html`'s assets are built with Vite `base: '/app/'` and consumed by a React Router with `basename: '/app'` (`ui/frontend/src/App.tsx`). When a bare Jinja path (e.g. `/investigations`, or, after 5.1–5.4, `/knowledge`, `/health/ingestion`, `/sources`, `/spending`, `/metrics`) is eventually added to `REACT_OWNED_PREFIXES`, the browser's `location.pathname` will be that bare path (Flask never redirects — `matches_react_prefix` short-circuits `before_request` and serves the shell directly at the original URL), which does **not** start with `/app`, so React Router's `basename: '/app'` matching will not resolve any route at that URL. This is untested today because `REACT_OWNED_PREFIXES` defaults to `()` in production and the only test exercising a non-empty registry checks HTTP-level shell-serving, not client-side route resolution. This doc does not resolve it (`REACT_OWNED_PREFIXES` is explicitly out of scope for Task 5.0) — it is flagged here so whoever performs the actual cutover (retiring a Jinja route in favor of its React equivalent, per FR50) budgets time to address the basename mismatch (e.g. dropping `basename` once cutover begins, or a redirect strategy) rather than discovering it as a live-site regression.

---

## 7. Later increment, target pinned — remaining nav routes

Not in Milestone 2.1's scope (5.1–5.4). Recorded so a future task can be scoped directly against this doc without re-deriving the inventory. None of these have an associated FR — templates are the sole target throughout.

| Nav label | Group | Jinja URL(s) | Dual-mode/HTMX | Parity target | Data source |
|---|---|---|---|---|---|
| Health | Observe | `/health/` | Full page ↔ `HX-Request` partial `health/_status_content.html`, `hx-trigger="every 5s"` | `templates/health/status.html` — no FR (general component-health overview; distinct from the ingestion/detection-stats route, §3) | `health_bp` / `HealthService.get_health()` |
| SLO | Observe | `/slo/` | Full page ↔ partial `slo/_content.html` | `templates/slo/dashboard.html` — no FR | `slo_bp` (`ui/beeper_ui/routes/slo.py`) / `SLOService` |
| Services | Observe | `/services/` | Full page ↔ partial `services/_list_content.html` | `templates/services/list.html` — no FR | `services_bp` (`ui/beeper_ui/routes/services.py`) / `ServiceHealthService` |
| Topology | Observe | `/topology/` | Full page ↔ partial `topology/_topology_content.html` | `templates/topology/index.html` — no FR | `topology_bp` (`ui/beeper_ui/routes/topology.py`) / topology service |
| Analytics | Learn | `/analytics/` | Full page ↔ partial `analytics/_dashboard_content.html` | `templates/analytics/dashboard.html` — no FR | `analytics_bp` (`ui/beeper_ui/routes/analytics.py`) |
| Reports | Learn | `/reports/executive` | Full page ↔ partial `reports/_executive_content.html` | `templates/reports/executive.html` — no FR | `reports_bp` (`ui/beeper_ui/routes/reports.py`) |
| Handoff | Learn | `/handoff/` | Full page ↔ partial `handoff/_content.html` | `templates/handoff/handoff.html` — no FR | `handoff_bp` (`ui/beeper_ui/routes/handoff.py`) / `HandoffService` |
| Cost Insights | Manage | `/spending/costs` (+ `/spending/costs/breakdown`, `/spending/costs/export`) | Full page ↔ partial `spending/_cost_breakdown.html` | `templates/spending/costs.html` — no FR (the Spending dashboard's FR, §4b, does not extend to this related-but-distinct breakdown view) | `spending_bp` (`ui/beeper_ui/routes/spending.py`) / `SpendingService` |
| Notifications | Manage | `/notifications/` | Full page ↔ partial `notifications/_channel_list.html` | `templates/notifications/config.html` — no FR | `notification_config_bp` (`ui/beeper_ui/routes/notification_config.py`) |
| Trust | Manage | `/settings/trust/` | Full page (no HTMX auto-refresh; sub-actions return result partials) | `templates/trust/settings.html` — no FR | `trust_settings_bp` (`ui/beeper_ui/routes/trust_settings.py`) / `TrustLevelService` |

---

## 8. Summary table (all 16 sidebar destinations, cross-reference)

| # | Nav label | Group | Task | Parity target section |
|---|---|---|---|---|
| 1 | Investigations | Observe | Shipped (Phase 1) | §1 |
| 2 | Sources | Observe | 5.3 | §4a |
| 3 | Health | Observe | Later increment | §7 |
| 4 | Ingestion Stats | Observe | 5.2 | §3 |
| 5 | SLO | Observe | Later increment | §7 |
| 6 | Services | Observe | Later increment | §7 |
| 7 | Topology | Observe | Later increment | §7 |
| 8 | Knowledge Base | Learn | 5.1 | §2 |
| 9 | Metrics | Learn | 5.4 | §5 |
| 10 | Analytics | Learn | Later increment | §7 |
| 11 | Reports | Learn | Later increment | §7 |
| 12 | Handoff | Learn | Later increment | §7 |
| 13 | Spending | Manage | 5.3 | §4b |
| 14 | Cost Insights | Manage | Later increment | §7 |
| 15 | Notifications | Manage | Later increment | §7 |
| 16 | Trust | Manage | Later increment | §7 |

---

## 9. Net-new React routes (no Jinja ancestor)

Every route block in §1–§7 above ports an EXISTING Jinja view — "parity"
means matching what the retired template already did. ADR 0002 (Milestone
2.3, Identity & Access) introduces the first React routes with **no Jinja
predecessor at all**: `/app/login` (Task 8.6) and, following it,
`/app/admin/users` (Task 8.7). Neither one has a template to port from or
retire — the UI was unauthenticated before ADR 0002, so there is nothing
upstream of these routes except the FR text itself. This section is the
convention for documenting that case, added by Task 8.6 per the ADR's own
§6 instruction ("`docs/design/route-parity-targets.md` gains a §9
'Net-new React routes (no Jinja ancestor)' block convention").

**Block shape:** every net-new route block uses the same `- **Field:**`
line set as §1–§5 above, with two differences the guard test
(`ui/tests/test_route_parity_targets.py`) enforces specifically for this
section:

- **`- **Jinja URL(s):**` is always the literal string `none (net-new)`** —
  never a real Jinja path (there isn't one) and never left blank (an empty
  field would be indistinguishable from an oversight). This is the marker
  the guard test's net-new-specific check looks for.
- **`- **Parity target:**` cites the FR id(s) that define "done" for a
  route with no template to diff against** — resolved against
  `docs/reqs/main.md` exactly like every other block's citation (the
  existing `_target_resolves()` check in the guard test needs no special
  casing for this: an FR id is an FR id regardless of which section cites
  it).

### 9a. Local login (`/app/login`)

- **Jinja URL(s):** none (net-new)
- **React URL (canonical, dev-time, under `/app`):** `/app/login`
- **REACT_OWNED_PREFIXES value (future cutover):** n/a — there is no bare
  Jinja path to redirect from; `/app/login` is reached directly (via a
  typed URL, a bookmark, or the `next=` redirect `resolve_request_identity()`
  emits for an unauthenticated page/API request in `local` mode).
- **Parity target:** FR59, FR61 — the uniform-401 local-login matrix
  (unknown-user/bad-password/deactivated indistinguishable, constant
  delay) and the bootstrap/recovery flow this page is the front door for.
  No template citation applies (net-new).
- **Dual-mode/HTMX:** N/A — never existed as a Jinja route; renders inside
  the React shell, outside the authenticated sidebar chrome (a minimal
  centered card, per ADR §6).
- **Permalink state to URL-encode:** `next` — the post-login redirect
  target, same-origin-validated both server-side
  (`beeper_ui.middleware.session.build_login_redirect_next()`) and
  client-side (`LoginPage.tsx`'s `resolveSafeNextPath()`; only a bare
  `/app` or `/app/...` path is honored, everything else falls back to
  `/app/investigations`).
- **Data source:** `POST /api/v1/auth/login` / `GET /api/v1/auth/me`
  (`ui/beeper_ui/routes/auth.py`) / `IdentityStoreService`
  (`ui/beeper_ui/services/identity_store.py`).
- **Scope / carve-outs:** the OIDC login flow (`GET /auth/login`, Task 8.5)
  is a server-redirect flow with no React page of its own — out of scope
  here.

### 9b. Admin users management (`/app/admin/users`) — implemented by Task 8.7

- **Jinja URL(s):** none (net-new)
- **React URL (canonical, dev-time, under `/app`):** `/app/admin/users`
- **REACT_OWNED_PREFIXES value (future cutover):** n/a (see §9a).
- **Parity target:** FR60 — user list/create/role-assign/deactivate/
  reactivate/password-reset, last-admin and SCIM-owned refusal states.
- **Dual-mode/HTMX:** N/A — net-new; renders inside the authenticated
  `AppLayout` sidebar shell (a Manage-group destination, unlike `/app/login`
  in §9a), role-gated as a UI affordance (`useCurrentUser().role ===
  "admin"` hides the nav item; the API — `require_role("admin")` on every
  route — is the actual enforcement boundary).
- **Permalink state to URL-encode:** none — no list filter/sort/pagination
  state in v1 (a fixed, admin-managed-scale user table per ADR §6's
  "minimal" scope).
- **Data source:** `admin_users_api_bp` (`/api/v1/admin/users`,
  `ui/beeper_ui/routes/admin_users.py`) / `IdentityStoreService`
  (`ui/beeper_ui/services/identity_store.py`).
- **Status:** **implemented (Task 8.7).** Registered whenever
  `BEEPER_AUTH_MODE != "none"` (`local` and `oidc`; never `none` — see that
  module's docstring for the registration + `oidc`-mode create-refusal
  decisions). Read/write states: `409 last-admin` (demote/deactivate the
  final active admin), `409 scim-owned-user` (write to a SCIM-linked
  record while in `oidc` mode), `409 local-user-creation-unavailable`
  (create attempted while in `oidc` mode).
