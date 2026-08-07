"""Tests for the RBAC posture decision on the six previously-ungated
`/api/v1/*` blueprints (Task 6.2a / ADR 0001 §0(a) item 4).

Decision: gate every read endpoint in these six blueprints with
`@require_role("user")`, matching the convention every other already-RBAC'd
blueprint uses for its reads (`trust_config`, `trust_settings`,
`confidence_gates`, `notifications`, `notification_config`, `reports` — see
ADR 0001 §1). Reasoning, recorded here because the decision has to be
*tested*, not just documented in prose:

1. **Consistency.** These are the only read-only JSON blueprints in the
   codebase that had no `require_role` gate at all — every other route with
   a comparable "read data" shape already carries `@require_role("user")`.
   Leaving them open was an omission, not a considered choice (confirmed:
   zero call sites before this task — see ADR 0001 §1's inventory, which
   lists 27 gates across 7 *other* files).
2. **No regression for the React UI.** React sends no auth header at all
   (Task 6.2b's scope, not 6.2a's) — `resolve_user_role()` always falls
   through to the default `"user"` role for those requests. A `"user"` gate
   never rejects a `"user"`- or `"admin"`-resolved caller (see
   `beeper_ui.middleware.permissions.require_role`: the 403 branch only
   fires for `role == "admin"` gates), so gating here is a pure structural/
   documentation change today, not a behavior change — proven below by
   asserting these routes are still reachable.
3. **Correct posture for Task 6.2b.** Once verified identity lands, a
   caller whose credential fails verification is meant to resolve to
   `"user"` (or be rejected outright — see ADR 0001 §0(a) item 2), never to
   `"admin"`. Having `@require_role("user")` already in place here means no
   route-level follow-up is needed when 6.2b ships; the gate is inert only
   because every caller today resolves to a role in `{"user", "admin"}` —
   nothing in the codebase, before or after this decision, can resolve to
   an unrecognized role that `require_role("user")` would actually reject.

The introspection tests below are the load-bearing proof of the decision:
`require_role()` stamps `.required_role` on the wrapped view function, so
this can be verified structurally without needing to provoke a 403 that,
per point 2 above, cannot currently occur.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

# (blueprint endpoint name, human label) for every GET route in the six
# previously-ungated blueprints named in the task (ADR 0001 §0(a) item 4 /
# Task 6.2a AC #2).
GATED_JSON_API_ENDPOINTS = [
    "investigations_api.investigations_list_json",
    "investigations_api.investigation_detail_json",
    "investigations_api.investigation_events_json",
    "knowledge_api.knowledge_list_json",
    "knowledge_api.knowledge_entry_json",
    "ingestion_api.ingestion_stats_json",
    "sources_api.sources_list_json",
    "spending_api.spending_json",
    "metrics_api.mttr_json",
    "metrics_api.mttr_drilldown_json",
]

# One representative, parameter-free GET path per blueprint, used for the
# behavioral (non-403) reachability check.
NO_PARAM_GET_PATHS = [
    "/api/v1/investigations/",
    "/api/v1/knowledge/",
    "/api/v1/ingestion/stats",
    "/api/v1/sources/",
    "/api/v1/spending/",
    "/api/v1/metrics/mttr",
]


class TestSixBlueprintsAreDeliberatelyGated:
    """Structural proof: every endpoint in the six previously-ungated
    blueprints now carries an explicit `@require_role("user")` decorator."""

    @pytest.mark.parametrize("endpoint", GATED_JSON_API_ENDPOINTS)
    def test_endpoint_has_required_role_user(self, app: Flask, endpoint: str) -> None:
        view = app.view_functions[endpoint]
        assert getattr(view, "required_role", None) == "user", (
            f"{endpoint} is missing the deliberate @require_role('user') gate "
            "(Task 6.2a / ADR 0001 §0(a) item 4)"
        )

    def test_all_ten_known_routes_are_present(self, app: Flask) -> None:
        """Guards against silently losing coverage if a route is renamed —
        fails loudly instead of the parametrized test above just not
        collecting that case."""
        missing = [e for e in GATED_JSON_API_ENDPOINTS if e not in app.view_functions]
        assert missing == []


class TestSixBlueprintsRemainReachable:
    """Behavioral proof: the gate does not break the React UI, which sends
    no auth header. Every route must still respond (200, or the route's own
    graceful degrade like a 503 "operator unavailable" or 400 "missing
    filters") — specifically NEVER 403, which would be a real regression.
    """

    @pytest.mark.parametrize("path", NO_PARAM_GET_PATHS)
    def test_default_anonymous_caller_is_not_blocked(self, client: FlaskClient, path: str) -> None:
        resp = client.get(path)
        assert resp.status_code != 403, (
            f"{path} rejected an unauthenticated (default-role) caller — "
            "the React UI sends no auth header today, this would break it"
        )

    @pytest.mark.parametrize("path", NO_PARAM_GET_PATHS)
    def test_user_role_caller_is_not_blocked(self, user_client, path: str) -> None:
        resp = user_client.get(path)
        assert resp.status_code != 403

    @pytest.mark.parametrize("path", NO_PARAM_GET_PATHS)
    def test_admin_role_caller_is_not_blocked(self, admin_client, path: str) -> None:
        resp = admin_client.get(path)
        assert resp.status_code != 403

    def test_mttr_drilldown_with_params_is_not_blocked(self, client: FlaskClient) -> None:
        """The one endpoint that needs query params to avoid its own 400
        (unrelated to RBAC) — exercised separately from the no-param list."""
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-01-01&end=2026-01-02")
        assert resp.status_code != 403
