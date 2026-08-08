"""Tests for the BFF route-dispatch registry (Task 1.3 / D11) and its
Task 6.3 (D13/D14) redirect cutover.

Historical [T] acceptance criteria (Task 1.3):
  1. A React-owned prefix returns the SPA shell; an UNMIGRATED route still
     renders its Jinja page.
  2. Collision test: for a path that exists in BOTH worlds, it resolves to
     the React shell WHEN its prefix is in the registry, and to Jinja when
     it is NOT — deterministic precedence, toggled at test time.

Task 6.3 changed step 1's *mechanism* (D14): a matched, non-excluded path
now 302-redirects to `/app/<path>` instead of being served the shell in
place — see the module docstring in `beeper_ui/routes/react_registry.py`
for why (the bundle's `base`/`basename` are hard-wired to `/app`, so serving
it at a bare path renders nothing). It also means AC2's "toggle the
registry, flip the outcome" demonstration no longer holds for the real
`/investigations` (or any of the other five migrated) blueprints, because
their Jinja view functions are now permanently gutted to a redirect
regardless of registry membership (Task 6.3's "render path removed" half of
its AC — see `TestGuttedViewsRedirectRegardlessOfRegistry` below). The
underlying registry mechanism (`matches_react_prefix` + the toggle) is still
exactly as before and is still proven here against a synthetic prefix that
has no gutted view function of its own.

The full end-to-end proof that the SIX real migrated prefixes redirect
correctly, that un-migrated/carved-out sub-routes survive, and that query
strings (FR53 permalinks) survive the hop lives in
`ui/tests/test_jinja_retirement.py` — this file covers the registry/dispatch
*mechanism* in isolation (unit tests + a couple of synthetic-prefix
integration tests); that file covers the *production* registry value and
every real route in `docs/design/route-parity-targets.md`.

Shell-serving assertions below require `ui/frontend/dist/` to exist (`npm
run build` in `ui/frontend/`), same as `test_react_shell.py` — if the dist is
absent they are skipped with an informative message.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.routes.react_registry import (
    build_app_redirect_target,
    matches_react_prefix,
)

_TESTS_DIR = Path(__file__).parent
_DIST = _TESTS_DIR.parent / "frontend" / "dist"

_DIST_MISSING_REASON = (
    f"frontend dist not built: run `npm run build` in ui/frontend/ first. "
    f"(looked for {_DIST})"
)


def _dist_available() -> bool:
    return (_DIST / "index.html").is_file()


MOCK_INVESTIGATIONS = [
    {
        "id": "inv-abc123",
        "status": "investigating",
        "service": "payments",
        "severity": "high",
        "condition": "High error rate detected",
        "started_at": "2026-02-09T12:00:00Z",
        "completed_at": None,
        "triggered_at": "2026-02-09T11:55:00Z",
    },
]


def _app_with_registry(prefixes: tuple[str, ...]) -> Flask:
    """Build a fresh app instance with a specific REACT_OWNED_PREFIXES value.

    A fresh app is required (rather than mutating app.config on a shared
    fixture) because the before_request hook reads the registry live from
    current_app.config on every request, so mutating config on an existing
    app instance would also work — but building fresh keeps each test
    hermetic and matches how the `app` fixture is normally constructed.
    """

    class _Config(TestingConfig):
        REACT_OWNED_PREFIXES = prefixes

    return create_app(_Config)


@pytest.fixture(autouse=True)
def _mock_urgency_deps():
    """Autouse: mock SLO/urgency service dependencies used by the Jinja list view."""
    with (
        patch("beeper_ui.routes.investigations._get_slo_service") as mock_slo,
        patch("beeper_ui.routes.investigations._get_urgency_service") as mock_urg,
    ):
        slo = MagicMock()
        slo.get_service_budget.return_value = None
        mock_slo.return_value = slo
        urg = MagicMock()
        urg.compute_batch_urgency.return_value = {}
        mock_urg.return_value = urg
        yield


# ── unit tests for the pure matching helper ─────────────────────────────────


class TestMatchesReactPrefix:
    """Unit tests for the prefix-matching predicate, independent of Flask."""

    def test_exact_prefix_match(self) -> None:
        assert matches_react_prefix("/investigations", ("/investigations",))

    def test_subpath_match(self) -> None:
        assert matches_react_prefix(
            "/investigations/inv-123", ("/investigations",)
        )

    def test_sibling_path_does_not_match(self) -> None:
        # "/investigations-archive" must NOT match prefix "/investigations"
        assert not matches_react_prefix(
            "/investigations-archive", ("/investigations",)
        )

    def test_unregistered_path_does_not_match(self) -> None:
        assert not matches_react_prefix("/health", ("/investigations",))

    def test_empty_registry_matches_nothing(self) -> None:
        assert not matches_react_prefix("/investigations", ())

    def test_api_prefix_always_excluded_even_if_registered(self) -> None:
        # Defensive: even if a caller mistakenly registers "/api", the JSON
        # API must never be shadowed by the SPA shell.
        assert not matches_react_prefix(
            "/api/v1/investigations", ("/api",)
        )

    def test_app_prefix_always_excluded_even_if_registered(self) -> None:
        assert not matches_react_prefix("/app/assets/index.js", ("/app",))

    def test_dotdot_segment_always_excluded_even_if_registered(self) -> None:
        # Found via Task 6.3 test migration: Werkzeug's test client (and
        # some raw HTTP clients) pass a literal `..` segment straight
        # through to `request.path` without normalizing it first. Such a
        # path must never be treated as React-owned — see
        # `_is_always_excluded()`'s docstring in react_registry.py.
        assert not matches_react_prefix(
            "/investigations/../../etc/passwd/confirm", ("/investigations",)
        )
        assert not matches_react_prefix(
            "/investigations/../../etc/passwd", ("/investigations",)
        )


# ── unit tests for the Task 6.3 redirect-target builder ─────────────────────


class TestBuildAppRedirectTarget:
    """`build_app_redirect_target()` — the D14 bare-path -> `/app/*` mapping."""

    def _target(self, app: Flask, path: str, query_string: str = "") -> str:
        with app.test_request_context(path, query_string=query_string):
            return build_app_redirect_target(path)

    def test_default_rewrite_prepends_app(self, app: Flask) -> None:
        assert self._target(app, "/sources/") == "/app/sources"

    def test_default_rewrite_preserves_dynamic_segment(self, app: Flask) -> None:
        assert (
            self._target(app, "/investigations/inv-abc123")
            == "/app/investigations/inv-abc123"
        )

    def test_bare_path_without_trailing_slash(self, app: Flask) -> None:
        assert self._target(app, "/knowledge") == "/app/knowledge"

    def test_health_ingestion_uses_target_override(self, app: Flask) -> None:
        # The React route is named differently (`ingestion-stats`), not a
        # 1:1 rewrite of the Jinja path.
        assert self._target(app, "/health/ingestion") == "/app/ingestion-stats"

    def test_knowledge_search_overrides_to_knowledge_base_path(self, app: Flask) -> None:
        # Search is a `?q=` query param on /app/knowledge in React, not its
        # own `/app/knowledge/search` route (route-parity-targets.md §2).
        assert self._target(app, "/knowledge/search") == "/app/knowledge"

    def test_metrics_mttr_overrides_to_metrics(self, app: Flask) -> None:
        assert self._target(app, "/metrics/mttr") == "/app/metrics"

    def test_metrics_mttr_drilldown_overrides_to_metrics(self, app: Flask) -> None:
        assert self._target(app, "/metrics/mttr/drilldown") == "/app/metrics"

    def test_spending_status_overrides_to_spending(self, app: Flask) -> None:
        assert self._target(app, "/spending/status") == "/app/spending"

    def test_query_string_is_appended(self, app: Flask) -> None:
        assert (
            self._target(app, "/knowledge/", query_string="q=timeout&entry_type=runbook")
            == "/app/knowledge?q=timeout&entry_type=runbook"
        )

    def test_no_query_string_no_trailing_question_mark(self, app: Flask) -> None:
        target = self._target(app, "/sources/")
        assert "?" not in target

    def test_override_target_also_gets_query_string_appended(self, app: Flask) -> None:
        # Overrides (search, mttr, spending status) still carry the query
        # string through even though the base path itself is remapped.
        assert (
            self._target(app, "/knowledge/search", query_string="q=disk+space")
            == "/app/knowledge?q=disk+space"
        )


# ── [T] AC 1: React-owned prefix -> redirect; unmigrated route -> Jinja ────


class TestReactOwnedPrefixVsUnmigratedRoute:
    """AC: a React-owned prefix 302-redirects; an unmigrated route stays Jinja."""

    def test_registered_test_prefix_redirects_to_app(self) -> None:
        """A harmless test-only prefix, once registered, 302-redirects under /app."""
        app = _app_with_registry(("/__react_test_prefix__",))
        client = app.test_client()

        response = client.get("/__react_test_prefix__/anything")

        assert response.status_code == 302
        assert response.headers["Location"] == "/app/__react_test_prefix__/anything"

    @pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
    def test_following_the_redirect_lands_on_the_spa_shell(self) -> None:
        """The redirect target actually resolves to the built React shell."""
        app = _app_with_registry(("/__react_test_prefix__",))
        client = app.test_client()

        response = client.get("/__react_test_prefix__/anything", follow_redirects=True)

        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "<!doctype html>" in data.lower() or "<html" in data.lower()

    @respx.mock
    def test_unmigrated_route_still_renders_jinja(self, client: FlaskClient) -> None:
        """`/health/` — never in REACT_OWNED_PREFIXES — is unaffected: still Jinja/HTML.

        (Was asserted against `/knowledge/` before Task 6.3 migrated Knowledge
        Base; `/health/` — the general operator-health overview, distinct
        from the now-migrated `/health/ingestion` — is a route-parity-
        targets.md §7 "later increment" destination and remains genuinely
        un-migrated.)
        """
        respx.get("http://mock-operator:8080/api/v1/health/components").mock(
            return_value=Response(200, json={"operator": {"status": "healthy"}})
        )
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(
                200,
                json={
                    "buffer_size": 0,
                    "buffered_count": 0,
                    "dropped_count": 0,
                    "is_full": False,
                },
            )
        )
        response = client.get("/health/")
        assert response.status_code != 404
        assert response.status_code != 302
        data = response.get_data(as_text=True)
        assert '<div id="root">' not in data


# ── [T] AC 2: collision precedence — mechanism vs. the Task 6.3 reality ─────


class TestRegistryTogglePrecedence:
    """AC: prefix membership deterministically drives redirect precedence.

    Uses the synthetic `/__react_test_prefix__` (which has no Jinja
    blueprint at all, so there's nothing to "collide" with) to prove the
    *mechanism* is registry-driven, not blueprint-registration-order-driven
    — exactly as Task 1.3 originally proved via `/investigations`. See
    `TestGuttedViewsRedirectRegardlessOfRegistry` below for why
    `/investigations` itself can no longer be used for this demonstration
    post-Task-6.3.
    """

    def test_toggle_registry_flips_precedence_on_synthetic_prefix(self) -> None:
        unregistered_app = _app_with_registry(())
        unregistered_response = unregistered_app.test_client().get(
            "/__react_test_prefix__/x"
        )
        assert unregistered_response.status_code == 404  # no such Jinja route

        registered_app = _app_with_registry(("/__react_test_prefix__",))
        registered_response = registered_app.test_client().get(
            "/__react_test_prefix__/x"
        )
        assert registered_response.status_code == 302
        assert registered_response.headers["Location"] == "/app/__react_test_prefix__/x"


class TestGuttedViewsRedirectRegardlessOfRegistry:
    """Task 6.3 (D13/D14) documents an intentional AC2 behavior change.

    The six migrated Jinja view functions (`list_investigations`,
    `investigation_detail`, `kb_index`, `kb_search`, `kb_entry`,
    `ingestion_stats`, `list_sources`, `spending_dashboard`,
    `spending_status`, `metrics_dashboard`, `mttr_partial`,
    `mttr_drilldown`) are now permanently gutted to a redirect — their
    "render path" is removed, not merely toggled off by the registry (see
    each function's docstring in its route module for why they're kept
    registered rather than deleted: `url_for()` call sites in retained
    templates). This means `/investigations/` (and the other five) now
    redirects even with an EMPTY `REACT_OWNED_PREFIXES` — the registry no
    longer gates it, unlike every other route this app has ever migrated.
    This is a deliberate, documented consequence of "retire" (this task)
    vs. "coexist" (Tasks 1.3-5.4), not a bug.
    """

    def test_investigations_redirects_even_with_empty_registry(self) -> None:
        app = _app_with_registry(())  # empty registry — no before_request match
        response = app.test_client().get("/investigations/")

        # The before_request hook does NOT intercept this (empty registry) —
        # dispatch reaches the real `list_investigations()` view, which
        # itself now unconditionally redirects.
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/investigations"

    def test_knowledge_index_redirects_even_with_empty_registry(self) -> None:
        app = _app_with_registry(())
        response = app.test_client().get("/knowledge/")

        assert response.status_code == 302
        assert response.headers["Location"] == "/app/knowledge"

    @respx.mock
    def test_investigation_action_route_is_unaffected_by_this(self) -> None:
        """Only the six gutted views behave this way — kept action routes
        (never gutted) still depend on real request handling, proving the
        gutting is scoped to exactly the six retired views, not a blanket
        blueprint-wide change."""
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-1").mock(
            return_value=Response(404)
        )
        app = _app_with_registry(())
        response = app.test_client().get("/investigations/inv-1/urgency")

        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert '<div id="root">' not in data


# ── always-excluded paths stay excluded even with a matching registry ──────


class TestAlwaysExcludedPaths:
    """/api/* and the SSE/JSON endpoints must never be shadowed by the shell."""

    @respx.mock
    def test_api_v1_investigations_unaffected_by_broad_registry(self) -> None:
        """Even a broad registered prefix must not shadow the JSON API."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )
        # Register root "/" (the broadest possible prefix) to prove /api/* is
        # still excluded unconditionally.
        app = _app_with_registry(("/",))
        client = app.test_client()

        response = client.get("/api/v1/investigations/", headers={"X-Beeper-Role": "user"})

        assert response.status_code == 200
        assert response.is_json
        body = response.get_json()
        assert isinstance(body, list)
        assert body[0]["id"] == "inv-abc123"

    @pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
    def test_app_mount_unaffected_by_broad_registry(self) -> None:
        """/app/* keeps being served by its own blueprint, not double-dispatched."""
        app = _app_with_registry(("/",))
        client = app.test_client()

        response = client.get("/app/")

        assert response.status_code == 200
