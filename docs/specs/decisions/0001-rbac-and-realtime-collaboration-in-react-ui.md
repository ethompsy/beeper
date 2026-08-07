# ADR 0001 — RBAC and real-time collaboration in the React UI

- **Status:** **Accepted** — `[H]` approved by the user 2026-08-06 (Task 6.1 AC). See §0 for the approved decisions, which **differ from this ADR's original recommendation on RBAC**.
- **Date:** 2026-08-04 (proposed) · 2026-08-06 (accepted)
- **Author:** Claude (Tech Lead), Task 6.1
- **Affects:** `ui/beeper_ui/middleware/permissions.py`, `ui/beeper_ui/websocket/`, `ui/beeper_ui/services/collaboration_service.py`, `ui/beeper_ui/templates/investigations/_collaboration_panel.html`, all `require_role`-gated routes, `ui/frontend/` (Task 6.2 implementation target), Task 6.3 (Jinja retirement)
- **Related:** `docs/plans/react-ui.md` — D12, Q1 (R3), Q6, Q7

## 0. Approved decision (`[H]`, 2026-08-06)

The user reviewed both recommendations below and approved:

### (a) RBAC — **PORT + HARDEN IDENTITY** *(goes beyond §4's recommendation)*

Port the two-tier role split to the React/BFF path **and** replace the spoofable identity source with a verified one. The user explicitly declined "port as-is": preserving a control that only looks like a security boundary was judged not acceptable to carry into the new UI. Concretely, Task 6.2 must:

1. **Port the gates** — the same `user`/`admin` split over the same route surface as each blueprint migrates (20 `user`, 7 `admin` per §1), with the BFF/API layer as the enforcement point. The 31 tests in `ui/tests/test_permissions.py` are the behavioral spec for the gate semantics.
2. **Verify the JWT signature** — replace the unverified `base64.urlsafe_b64decode` payload peek in `resolve_user_role()` with real validation (K8s TokenReview API, or JWKS/public-key verification). A token that fails verification must resolve to the default `user` role (or be rejected outright) — never to `admin`.
3. **Gate the `X-Beeper-Role` header to non-production.** It may remain a development affordance, but `ProductionConfig` must refuse it. This is currently pinned by `test_permissions.py::test_header_sets_admin_role`, so **that test must be updated, not deleted** — the header path stays tested for development and gains a production-refusal test.
4. **Decide the JSON API's posture** — `investigations_api_bp` carries no `require_role` gate today (§3). Task 6.2 must consciously choose whether the React-consumed read endpoints stay open or gain a `user` gate, rather than inheriting the gap by omission.

**Scope consequence, recorded deliberately:** this makes the RBAC a genuine security boundary for the first time, and enlarges Task 6.2 beyond a pure migration task (§4 costed this as "L–XL, likely its own initiative"). If it proves too large to carry inside 6.2, split the hardening (items 2–3) into its own task rather than silently reverting to port-as-is — the approved decision is that the migrated UI does **not** ship the spoofable identity source.

### (b) SocketIO collaboration — **DROP, PRESERVE DATA**

Retire the surface exactly as §5's Drop option describes, with §6's data treatment as an explicit condition rather than an incidental detail: the Qdrant `collaboration_messages` collection is **left in place and not deleted**, so existing chat/annotation history remains recoverable if the decision is ever revisited. `/socket.io/*` returns the `410 Gone` + `application/problem+json` response specified in §6.

This directly addresses risk §7.3: the destructive part of Drop (discarding collaboration records) is **not** authorized — only the code surface is retired. Task 6.2 must not add a data-deletion step.

**Still worth confirming before 6.2 executes** (§7.4): `kb_relevance_feedback` is the one fully-functional event being retired. If no other path collects KB relevance feedback in the React UI, that is a small real capability loss — flag it rather than letting it disappear silently.

---

## Summary

> **Superseded on RBAC by §0.** The "Port as-is" recommendation below was NOT the approved outcome — the user chose Port + harden. The inventory, analysis, and options matrices remain accurate and are retained as the reasoning record.

1. **RBAC — recommend PORT (preserve current behavior in React/BFF).** The mechanism is real code with real tests, but its identity source is **trivially spoofable by any HTTP client** (a raw `X-Beeper-Role` header, or an unsigned-and-unverified JWT payload) — it is **not a security boundary today**, only a UI-affordance / fat-finger guard for admin-tier mutations. Porting preserves that guard-rail and existing test coverage without expanding Task 6.2's scope into building real authentication, which is a separate initiative.
2. **SocketIO collaboration — recommend DROP.** It is unreachable from the already-migrated React investigation detail view (zero references in `ui/frontend/`), invisible across 12+ Milestone 1.2–4.x plan entries that repeatedly touched that same view, and — critically — **three of its four "action" verbs (`approve_fix`, `reject_fix`, `redirect`) already silently no-op against the operator**: the REST endpoints they forward to (`/annotate`, `/redirect`, `/approve`, `/reject-fix`) do not exist in `operator/src/api.rs`. Porting would mean rebuilding a socket.io React client for a feature nobody's UI-facing code currently exercises and that's already broken where it matters.

Both are detailed below with full inventories, options matrices, and defined drop-responses for Task 6.2.

---

## 1. RBAC inventory

`ui/beeper_ui/middleware/permissions.py` implements `init_permissions(app)` (registers a `before_request` role resolver) and `require_role(role)` (route decorator, `"user"` or `"admin"`). 27 route-level call sites across 7 files:

| # | Blueprint (`url_prefix`) | File:line | Method + Path | Function | Role |
|---|---|---|---|---|---|
| 1 | `confidence_gates` (`/api/v1/trust/gates`) | `confidence_gates.py:70` | `POST /evaluate` | `evaluate_gate` | user |
| 2 | `confidence_gates` | `confidence_gates.py:177` | `GET /` | `list_gate_thresholds` | user |
| 3 | `confidence_gates` | `confidence_gates.py:205` | `GET /<int:trust_level>` | `get_gate_threshold` | user |
| 4 | `confidence_gates` | `confidence_gates.py:249` | `PUT /<int:trust_level>` | `update_gate_threshold` | **admin** |
| 5 | `trust_settings` (`/settings/trust`) | `trust_settings.py:62` | `GET /` | `trust_settings_page` | user |
| 6 | `trust_settings` | `trust_settings.py:94` | `POST /<service_name>/update` | `update_trust_level` | **admin** |
| 7 | `trust_settings` | `trust_settings.py:156` | `GET /gates` | `gate_thresholds_section` | user |
| 8 | `trust_settings` | `trust_settings.py:179` | `POST /gates/<int:trust_level>/update` | `update_gate_threshold` | **admin** |
| 9 | `trust_settings` | `trust_settings.py:256` | `GET /history` | `threshold_history_page` | user |
| 10 | `trust_settings` | `trust_settings.py:263` | `GET /history/content` | `threshold_history_content` | user |
| 11 | `trust_settings` | `trust_settings.py:288` | `POST /adjustments/<adjustment_id>/apply` | `apply_adjustment` | **admin** |
| 12 | `trust_settings` | `trust_settings.py:325` | `POST /adjustments/<adjustment_id>/reject` | `reject_adjustment` | **admin** |
| 13 | `trust_settings` | `trust_settings.py:362` | `GET /adaptive/tuning` | `adaptive_tuning_section` | user |
| 14 | `trust_settings` | `trust_settings.py:388` | `POST /adaptive/evaluate/<service_name>` | `evaluate_service_threshold` | **admin** |
| 15 | `trust_config` (`/api/v1/trust`) | `trust_config.py:58` | `GET /services` | `list_trust_levels` | user |
| 16 | `trust_config` | `trust_config.py:83` | `GET /services/<name>` | `get_trust_level` | user |
| 17 | `trust_config` | `trust_config.py:129` | `PUT /services/<name>` | `update_trust_level` | **admin** |
| 18 | `trust_config` | `trust_config.py:229` | `GET /definitions` | `get_trust_definitions` | user |
| 19 | `notifications` (`/api/v1/notifications`) | `notifications.py:43` | `POST /deliver` | `deliver_notification` | user |
| 20 | `notifications` | `notifications.py:109` | `POST /digest/flush` | `flush_email_digest` | user |
| 21 | `notifications` | `notifications.py:211` | `GET /audit` | `get_notification_audit` | user |
| 22 | `notification_config` (`/notifications`) | `notification_config.py:34` | `GET /` | `list_channels` | user |
| 23 | `notification_config` | `notification_config.py:67` | `POST /test` | `test_channel` | user |
| 24 | `reports` (`/reports`) | `reports.py:65` | `GET /noise` | `noise_report` | user |
| 25 | `reports` | `reports.py:136` | `GET /executive` | `executive_report` | user |
| 26 | `investigations` (`/investigations`) | `investigations.py:944` | `POST /<investigation_id>/verify` | `verify_investigation` | user |
| 27 | `investigations` | `investigations.py:1229` | `POST /<investigation_id>/feedback` | `submit_investigation_feedback` | user |

**Totals: 20 `user`, 7 `admin`.** Every admin-tier gate protects a *mutation* (trust-level writes, gate-threshold writes, adjustment apply/reject, adaptive evaluate) — no admin-gated reads exist. `ui/tests/test_permissions.py` has 31 tests covering this decorator's behavior directly.

### Identity-source finding — stated plainly

`resolve_user_role()` (a `before_request` hook, always active — no environment gate) resolves `g.user_role` via, in order:

1. **`Authorization: Bearer <token>`** — decodes the JWT payload (`base64.urlsafe_b64decode` on the middle segment) and checks for `"beeper-admin"` in the `groups` claim. **The signature is never verified** — there is no call to the K8s TokenReview API, no JWKS/public-key check, nothing. Any client can construct a 3-segment, base64-JSON-decodable string with `{"groups": ["beeper-admin"]}` in the payload and be granted `admin`.
2. **`X-Beeper-Role` header** — read verbatim from the request; `"admin"` or `"user"` is accepted as-is. The code comment calls this "development mode," but nothing in `permissions.py` or `config.py` (including `ProductionConfig`) restricts this path to non-production — it is live in every environment. `ui/tests/test_permissions.py::test_header_sets_admin_role` confirms this is intentional, tested behavior, not a latent bug.
3. **Default** — `"user"` if neither is present.

**Conclusion: this is not a genuine security control as deployed.** Both paths are attacker-controlled with zero server-side verification. It functions correctly as a **UI-affordance / operational safety-rail** — it stops an *honest* operator's browser from rendering admin controls or POSTing to admin routes by accident, and the 403 RFC7807 response is well-formed — but it provides no protection against anyone willing to set one HTTP header. Whether that gap matters depends entirely on deployment topology (is this UI reachable only from a trusted internal network / port-forward, or is it internet-facing?) — that question is out of this task's scope but material to whichever option is chosen below, and is flagged in Risks (§8).

---

## 2. SocketIO inventory

`ui/beeper_ui/websocket/__init__.py` (`init_socketio`, called from `app.py:71`) + `ui/beeper_ui/websocket/investigation.py` (handlers). No `require_role` or any auth check gates any event or the connection itself — `_get_user()` returns `g.user_role` ("admin"/"user"), **not a per-person identity**, so two different "user"-role people in the same room are indistinguishable in the transcript.

| Event | Payload | Mutates | Persists? | Operator-side effect |
|---|---|---|---|---|
| `join_investigation` | `{investigation_id, last_seen_timestamp?}` | joins SocketIO room; adds to in-memory active-user map; emits history | Active-user map: **in-memory only**, lost on restart | none |
| `leave_investigation` | `{investigation_id}` | removes from room + active-user map | same as above | none |
| `send_message` | `{investigation_id, content}` | stores + broadcasts a chat message | **Qdrant** `collaboration_messages` collection — durable, survives restart | none (chat only) |
| `annotate` | `{investigation_id, text}` | stores + broadcasts an annotation | **Qdrant** — durable | **Attempts** `POST {operator}/api/v1/investigations/{id}/annotate` — **endpoint does not exist on the operator** (see below); failure is caught and only logged (`logger.warning`), so the UI reports success regardless |
| `redirect` | `{investigation_id, instruction}` | stores + broadcasts a redirect | **Qdrant** — durable | **Attempts** `POST .../redirect` — **endpoint does not exist**; same silent-failure pattern |
| `approve_fix` | `{investigation_id}` | stores + broadcasts an approval | **Qdrant** — durable | **Attempts** `POST .../approve` — **endpoint does not exist**; same silent-failure pattern |
| `reject_fix` | `{investigation_id, reason?}` | stores + broadcasts a rejection | **Qdrant** — durable | **Attempts** `POST .../reject-fix` — **endpoint does not exist**; same silent-failure pattern |
| `kb_relevance_feedback` | `{investigation_id, entry_id, is_relevant}` | records feedback via `KBSurfacingService` (real, separate code path — verified to exist), stores + broadcasts | **Qdrant** (both the KB feedback payload and the collaboration message) — durable | Real (KB surfacing service, not the operator investigation API) |
| `disconnect` | — | cleans up active-user map across all rooms, broadcasts `user_left` | in-memory only | none |

### The four "action" verbs don't do what the UI implies

`operator/src/api.rs` registers exactly these investigation routes: `GET /api/v1/investigations`, `GET /api/v1/investigations/:id`, `POST .../confirm`, `POST .../reject` (rejects a *resolution*, a different flow from `reject_fix`), `POST .../resolve`, `POST .../verify`. **There is no `/annotate`, `/redirect`, `/approve`, or `/reject-fix` route anywhere in the operator or investigator crates** (grepped both; zero matches). So `handle_annotate`/`handle_redirect`/`handle_approve_fix`/`handle_reject_fix` in `investigation.py` each POST to a 404 on the operator, catch the resulting exception, log a warning, and **proceed to broadcast success to the room anyway** (`emit("fix_approved", ...)`, etc.). An operator clicking "Approve" today gets a chat message saying they approved the fix; nothing on the investigation actually changes.

### Reachability and usage assessment

- **Template inclusion:** `_collaboration_panel.html` is unconditionally included in `templates/investigations/detail.html:50` — the **Jinja** investigation detail page.
- **React coexistence state:** `REACT_OWNED_PREFIXES` (the D11 dispatch registry that lets a React route deterministically win over its Jinja twin) defaults to `()` — empty, in every config including production (`ui/beeper_ui/config.py:32`). So the bare `/investigations/<id>` URL is still Jinja-served today; the React detail view lives at `/app/investigations/<id>` and is what the migrated sidebar nav (Task 2.1) actually links to.
- **React has zero references to it.** No `socket.io-client` in `ui/frontend/package.json`; no `socket`/`collab` string anywhere in `ui/frontend/src/`. The extensive Milestone 1.2/1.3/4.x changelog for the investigation detail view (Tasks 2.1, 2.5, 2.6a, 2.6b, 3.2, 4.1, 4.2 — 7+ separate merges, all touching that exact page) **never mentions collaboration, annotations, approvals, or SocketIO once.** The live-update channel React did build (2.6a/2.6b's SSE `useInvestigationEvents`) is a *different*, already-shipped mechanism for step-progress streaming — it is not a gap this feature would need to fill.
- **Tests:** `ui/tests/test_websocket.py` (60 tests) and `ui/tests/test_collaboration_service.py` (20 tests) give solid *mechanical* coverage (join/leave/broadcast/persistence/RFC7807-adjacent error shapes) — but they mock the operator forward calls, so they don't (and structurally can't, from inside this repo's test suite) catch that the target operator endpoints don't exist. The code is well-tested; the feature it implements is half wired to nothing.
- **No connect-time auth, no room-membership check, no investigation-existence check** in `handle_join` — any client can join any `investigation_id` room name and post to it.

**Assessment: this is unexercised, partially non-functional scaffolding**, not an in-use collaboration surface. It was clearly built with real engineering care (Qdrant persistence, RFC7807-style error emits, reconnection history replay) but the operator-side integration was never completed, and the React migration has organically routed around it for 12+ weeks of plan history without anyone flagging it as a gap — consistent with it not being used.

---

## 3. Interaction with the migration

- **Milestone 2.1** (Task 5.1–5.4: KB, ingestion/detection stats, sources, spending, metrics) touches none of the RBAC- or SocketIO-bearing blueprints above — no overlap, no conflict.
- **Investigation detail** (`investigations_bp`, RBAC sites #26–27) is already migrated (Milestone 1.2) — the React detail page does not call `verify_investigation` or `submit_investigation_feedback` yet (React only consumes `investigations_api_bp`'s read endpoints, which carry **no** `require_role` gate today). Porting RBAC for Task 6.2 needs to cover these two actions if/when React adds verify/feedback UI, plus decide whether the *unguarded* JSON API blueprint should gain gates too (out of this ADR's scope to decide the specific guard shape — that's Task 6.2).
- **Gap for the orchestrator to weigh, found incidentally:** `trust_config`, `trust_settings`, `confidence_gates`, `notifications`, `notification_config`, and `reports` — i.e. **every admin-tier RBAC gate in the inventory** — belong to blueprints that are **not listed anywhere in Milestone 2.1's route scope** (5.1–5.4 cover KB/health/sources+spending/metrics only) and are **not mentioned anywhere else in `docs/plans/react-ui.md`**. Task 6.3's AC ("no route is served by Jinja... all routes return the React shell") will orphan these six blueprints unless Task 5.0's in-progress route inventory adds them to scope, or a separate task is created. This ADR does not resolve that gap (it's Task 5.0's territory) but flags it because it directly bears on Task 6.2: whichever RBAC decision is approved has to be portable to routes that currently have no planned React destination.
- **Task 6.3** ("delete Jinja templates + the Flask render path") would delete `_collaboration_panel.html` and `investigation-collab.js` outright once the Jinja `investigations/detail.html` is removed — consistent with a Drop decision for SocketIO; if Preserve/Port were chosen instead, Task 6.3 would need a carve-out to keep the Jinja panel alive (undermining "no route served by Jinja") or Task 6.2 would need to build a React replacement first.

---

## 4. Decision (a): Two-tier RBAC

| Option | Description | Effort | Risk | Consequence |
|---|---|---|---|---|
| **Port (recommended)** | Reimplement `require_role`-equivalent gating in the React/BFF path with the **same identity-resolution mechanism** (header + unverified-JWT-groups-claim), applied to the same route set as it's migrated | M — new gate on the BFF/API layer, admin/user React route guards, tests per Task 6.2 AC | Low regression risk (preserves current behavior + the 31 existing tests as a reference); **but** perpetuates a control that looks stronger than it is if not clearly documented | Existing admin/user distinction and fat-finger protection survive the migration unchanged; no new auth infra required |
| Preserve (Jinja stays for these routes) | Carve the 6 RBAC-bearing Jinja blueprints out of Task 6.3's scope, leave them un-migrated indefinitely | S (no work) | Contradicts Task 6.3's AC ("no route served by Jinja"); leaves a permanent Jinja island | Not viable as a long-term answer — only defers the decision |
| Drop | Remove the admin/user split entirely; all authenticated (or all default-`user`) requests treated equally in React/BFF | S–M (delete gate, update the 7 admin routes' behavior, add Task 6.2's defined-response contract) | Removes the fat-finger guard-rail on trust-level and gate-threshold writes — a real, if modest, product regression; no security loss since there was none to begin with | Simplest surface, but a behavior change users may not expect |
| Build real auth first, then port | Replace the identity source with a verified one (K8s TokenReview API call, or OIDC/SSO), *then* port RBAC on top of it | L–XL, and out of proportion to a UI-migration task; likely its own initiative | High if rushed (auth is easy to get subtly wrong); but this is the only option that makes the RBAC a genuine security boundary | Correct long-term fix, wrong scope for Task 6.2 |

**Recommendation: Port**, unchanged identity-resolution mechanism, unchanged role split, ported to whatever route surface each blueprint ends up on (React/BFF guard for the JSON API, React route guard for anything client-rendered). Rationale: it's the lowest-regression path, matches the plan's own framing at Q1 ("preserve the two-tier RBAC... in React/BFF"), reuses 31 existing tests as a spec, and doesn't inflate Task 6.2 into a real-authentication project. The one condition attached to this recommendation: **this ADR should not be read as certifying the mechanism as secure** — if Beeper's deployment story is or becomes internet-facing or multi-tenant, "Build real auth first" needs to be revisited as its own decision, separate from this migration.

---

## 5. Decision (b): SocketIO collaboration surface

| Option | Description | Effort | Risk | Consequence |
|---|---|---|---|---|
| **Drop (recommended)** | Remove `ui/beeper_ui/websocket/`, `collaboration_service.py`, the Jinja panel + JS (falls out naturally with Task 6.3), and the operator-forwarding calls in `investigation_service.py` | S–M — deletion + Task 6.2's defined-response contract for the socket.io mount (§6) | Low — feature has no evidence of active use, and 3/4 of its actions are already non-functional; historical Qdrant data is left in place (no data-loss risk, just stops growing) | Simplifies the codebase; removes a UI element that currently misleads operators into thinking "Approve/Reject/Redirect" changed investigation state |
| Port (rebuild in React) | Add `socket.io-client`, build a React collaboration panel + hooks (join-room lifecycle tied to route mount, reconnection, history replay — comparable scope to 2.6a/2.6b's SSE work) | L — new dependency, new component family, new BFF-side auth decision (§4) needs to apply here too | Would be **porting broken functionality** unless the operator-side `/annotate` `/redirect` `/approve` `/reject-fix` endpoints are built first (separate, uncosted operator work, outside this UI plan) — real risk of shipping a "looks-functional-but-isn't" feature a second time | Restores real-time chat + presence, but the three action verbs stay theater until the operator is extended |
| Partial port — chat/annotations only | Keep only `send_message` + `annotate` (both **do** persist meaningfully to Qdrant and don't depend on the missing operator endpoints for their record-keeping value — `annotate`'s operator-forward attempt would just be dropped), rebuild as a lightweight React "comments" panel; drop `redirect`/`approve_fix`/`reject_fix`/presence | M | Medium — still new React surface + BFF auth wiring for a feature with no demonstrated demand; smaller than full Port but not free | A middle ground if the user believes a persisted-comments feature has value independent of the broken operator actions |
| Preserve (Jinja stays) | Same objection as RBAC's Preserve option — contradicts Task 6.3 | S | Contradicts Task 6.3's AC | Not viable long-term |

**Recommendation: Drop.** Rationale: zero React-side references across 12+ weeks / 7+ merges that repeatedly touched the exact page this panel lives on; three of its four action verbs already silently no-op against the operator (confirmed by grepping the operator/investigator crates — the endpoints simply don't exist); and dropping it directly serves Task 6.3's "no route served by Jinja" goal instead of requiring a carve-out or a rebuild. If the user has independent knowledge that this panel *is* used operationally (e.g., verbally, outside what the plan/tests/code capture), the "Partial port — chat/annotations only" option is the fallback worth revisiting, since that's the only part of the feature that's actually wired to something real (Qdrant persistence).

---

## 6. Defined responses for dropped surfaces (Task 6.2 requirement)

Task 6.2's AC requires any dropped feature to return "a defined response, not a 500." If the SocketIO Drop recommendation is approved, Task 6.2 should implement:

- **`/socket.io/*` (all methods — Engine.IO polling + WebSocket upgrade attempts):** since `init_socketio(app)` is removed, Flask's default 404 would fire (not a 500, but an unstyled HTML 404, inconsistent with the app's RFC7807 convention used elsewhere, e.g. `permissions.py`). Recommend registering an explicit low-priority route instead:
  - **Status:** `410 Gone`
  - **Headers:** `Content-Type: application/problem+json`
  - **Body:**
    ```json
    {
      "type": "https://beeper.dev/errors/feature-retired",
      "title": "Collaboration Feature Retired",
      "status": 410,
      "detail": "Real-time investigation collaboration (chat/annotations/approvals/redirections) was retired during the React migration. See docs/specs/decisions/0001-rbac-and-realtime-collaboration-in-react-ui.md.",
      "instance": "/socket.io/"
    }
    ```
- **`investigation_service.annotate_investigation` / `redirect_investigation` / `approve_fix` / `reject_fix`:** these are internal helper methods, not routes — delete them along with their only caller (the socket handlers). No external response contract needed.
- **Historical Qdrant `collaboration_messages` data:** out of scope to delete; leave in place. No route reads it once the handlers are removed, so it becomes inert, recoverable-if-ever-needed data rather than something requiring a migration.

If instead the RBAC Drop option is chosen (not the recommendation), the equivalent contract is simpler: the 7 currently-admin routes stop returning 403 for non-admin callers and behave exactly as their `user`-tier siblings — no new error surface needed, since removing a restriction doesn't introduce a new failure mode.

---

## 7. Risks and open items for the user to weigh

1. **RBAC's identity source is spoofable regardless of which option is chosen for this ADR**, except "Build real auth first." Porting preserves the *status quo* risk level, it does not increase or fix it — worth an explicit yes/no from the user rather than assuming "port" implies "this is now secure."
2. **Six RBAC-bearing Jinja blueprints (`trust_config`, `trust_settings`, `confidence_gates`, `notifications`, `notification_config`, `reports`) have no planned React destination** anywhere in `docs/plans/react-ui.md` today. This ADR flags it; resolving it is Task 5.0's (in-progress) route-inventory territory, not this task's. Task 6.2/6.3 will need that gap closed before "no route served by Jinja" can be true.
3. **If the SocketIO Drop recommendation is wrong** (i.e., collaboration is used in ways not visible from code/tests/plan history — e.g., a live demo script or an operator workflow not captured here), dropping it destroys working chat/annotation history for any investigation currently being collaborated on. Worth a direct confirmation from the user before Task 6.2 executes the deletion, not just silent approval of this ADR.
4. **`kb_relevance_feedback` is the one SocketIO event that's fully real** (persists to Qdrant via `KBSurfacingService`, no broken operator dependency) — if SocketIO is dropped wholesale, confirm there's no other, non-collaboration-panel path already planned to collect KB relevance feedback in the React UI; if not, this is a small, real capability loss worth a one-line callout even though the recommendation still holds (it's a minor loss weighed against retiring 7 other broken/unused events plus the whole websocket subsystem).
5. This ADR does not modify any code — `permissions.py`, `websocket/`, routes, and React source are all unchanged. It also does not correct `docs/specs/architecture.md`'s "no auth / SSE only" claim (tracked separately as Q7, plan-level, out of this task's scope) — that correction should reference this ADR's identity-source finding once written.

---

## 8. Implementation note — Task 6.2a (completed 2026-08-07)

Item 5 above is now out of date: code has been modified. Pre-work on Task 6.2
found the "harden identity" half of §0(a) is under-specified, not just large —
the UI has no JWT/crypto/kubernetes dependency, no ServiceAccount (`helm/beeper`
sets no `serviceAccountName` for the UI Deployment, and no `ui-serviceaccount
.yaml`/ClusterRole exists for a TokenReview call), React sends no auth header
and has no shared fetch wrapper, and most fundamentally there is **no
authentication at all** in the UI to verify an identity from. That question is
now tracked as **Q11** in `docs/plans/react-ui.md` and blocks a follow-on task,
**6.2b**. Per this ADR's own §4 fallback ("split the hardening into its own
task rather than silently reverting to port-as-is"), Task 6.2 was split:

- **6.2a (this note) — everything achievable now, fail-closed.** Completed:
  - Ported the `user`/`admin` gate to the six previously-ungated read-only
    `/api/v1/*` JSON blueprints (§0(a) item 4) — `investigations_api_bp`,
    `knowledge_api_bp`, `ingestion_api_bp`, `sources_api_bp`,
    `spending_api_bp`, `metrics_api_bp` — matching the `user`-gate convention
    every other read route in the codebase already used.
  - **`X-Beeper-Role` is refused under `ProductionConfig`** (§0(a) item 3) via
    a class attribute (`Config.ALLOW_ROLE_HEADER`), read by
    `resolve_user_role()` — *not* `ProductionConfig.__init__`, which is dead
    code under `Flask.config.from_object(<class>)` (no instantiation occurs).
    Still honored in development/testing.
  - Fixed an unrelated crash found during this work: a crafted JWT whose
    payload segment is valid JSON but not an object (e.g. the bare integer
    `123`) crashed `_extract_role_from_k8s_token`'s `claims.get(...)` with an
    uncaught `AttributeError` inside the `before_request` hook — 500ing every
    route. Now returns `None` (falls through) for any non-dict payload.
  - Item 2 of §0(a) — **verifying the JWT signature** — was **not** done. It
    requires the identity chain in the paragraph above, which does not exist
    yet. This is 6.2b, blocked on Q11.
  - Dropped the SocketIO surface per §0(b): `websocket/`, the Jinja
    `_collaboration_panel.html` + `investigation-collab.js` + its CSS, and
    the operator-forwarding helpers on `InvestigationService` (`annotate
    _investigation`, `redirect_investigation`, `approve_fix`, `reject_fix`)
    are removed. `collaboration_service.py` is **kept** (not just "costs
    nothing to leave" — it is still read by the Jinja investigation-detail
    view's "human interventions" history). `/socket.io/*` returns the exact
    `410 Gone` body from §6. **The `collaboration_messages` Qdrant collection
    is untouched** — no code path anywhere in the repo issues a delete/drop
    against it.
  - §7.4's flagged gap is confirmed, not resolved: `kb_relevance_feedback`
    was the one fully-functional SocketIO event, and dropping it is a real,
    if small, capability loss — no other path in the React UI collects KB
    relevance feedback today. Out of 6.2a's scope to add one.

- **6.2b (follow-on, blocked on Q11) — verified identity.** Real
  signature/identity verification, plus the K8s identity chain the UI
  currently lacks (ServiceAccount, RBAC for TokenReview or equivalent), so a
  token that fails verification resolves to `user` (or is rejected), never
  `admin`.

**Operational consequence, flagged per this ADR's own instruction not to hide
it:** refusing the spoofable header in production, with 6.2b not yet built,
means **production has no path to the `admin` role at all** — every
`@require_role("admin")` route 403s for every caller there until 6.2b ships.
This is the intended fail-closed behavior, weighed against the UI's
ClusterIP / non-internet-facing deployment. Documented in
[`docs/deployment-guide.md`](../../deployment-guide.md#beeper-ui-role-based-access-control-task-62a)
("RBAC and Security" → "Beeper UI role-based access control") for operators,
and in `beeper_ui/config.py`'s `ProductionConfig`/`ALLOW_ROLE_HEADER` comments
for developers.
