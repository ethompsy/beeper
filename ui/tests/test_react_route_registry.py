"""Tests for Task 1.3: BFF route-dispatch registry (D11).

Acceptance criteria [T]:
  1. A React-owned prefix returns the SPA shell; an UNMIGRATED route still
     renders its Jinja page.
  2. Collision test: for a path that exists in BOTH worlds (`/investigations`),
     it resolves to the React shell WHEN its prefix is in the registry, and
     to Jinja when it is NOT — deterministic precedence, toggled at test time.

These tests require `ui/frontend/dist/` to exist (`npm run build` in
ui/frontend/), same as test_react_shell.py, since the React shell path
returns the built index.html. If the dist is absent, the shell-serving
assertions are skipped with an informative message; the "still-Jinja"
half of each test does not depend on the dist and always runs.
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
from beeper_ui.routes.react_registry import matches_react_prefix

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


# ── [T] AC 1: React-owned prefix -> shell; unmigrated route -> Jinja ────────


class TestReactOwnedPrefixVsUnmigratedRoute:
    """AC: a React-owned prefix serves the shell; an unmigrated route stays Jinja."""

    @pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
    def test_registered_test_prefix_returns_spa_shell(self) -> None:
        """A harmless test-only prefix, once registered, returns the SPA shell."""
        app = _app_with_registry(("/__react_test_prefix__",))
        client = app.test_client()

        response = client.get("/__react_test_prefix__/anything")

        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "<!doctype html>" in data.lower() or "<html" in data.lower()

    @respx.mock
    def test_unmigrated_route_still_renders_jinja(self, client: FlaskClient) -> None:
        """/knowledge (never in the registry) is unaffected — still Jinja/HTML."""
        response = client.get("/knowledge/")
        # Rendered by the Jinja knowledge blueprint; must not be the SPA shell.
        assert response.status_code != 404
        data = response.get_data(as_text=True)
        assert '<div id="root">' not in data


# ── [T] AC 2: collision test — deterministic precedence toggle ─────────────


class TestInvestigationsCollisionPrecedence:
    """AC: `/investigations` resolves to React iff its prefix is registered."""

    @respx.mock
    def test_investigations_renders_jinja_when_not_registered(self) -> None:
        """Registry does NOT contain '/investigations' -> Jinja page renders."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )
        app = _app_with_registry(())  # empty registry (production default)
        client = app.test_client()

        response = client.get("/investigations/")

        assert response.status_code == 200
        assert b"inv-abc123" in response.data
        data = response.get_data(as_text=True)
        assert '<div id="root">' not in data

    @pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
    def test_investigations_renders_react_shell_when_registered(self) -> None:
        """Registry DOES contain '/investigations' -> React shell wins, deterministically.

        Note: no respx mock is installed here — if this fell through to the
        Jinja view it would raise/500 on the un-mocked operator call, so a
        200 SPA-shell response also proves Jinja's view function never ran.
        """
        app = _app_with_registry(("/investigations",))
        client = app.test_client()

        response = client.get("/investigations/")

        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "<!doctype html>" in data.lower() or "<html" in data.lower()

    @pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
    def test_investigations_detail_subpath_also_wins_when_registered(self) -> None:
        """Sub-paths under a registered prefix (e.g. detail view) also go to React."""
        app = _app_with_registry(("/investigations",))
        client = app.test_client()

        response = client.get("/investigations/inv-abc123")

        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "<!doctype html>" in data.lower() or "<html" in data.lower()

    @respx.mock
    def test_toggle_registry_flips_precedence_on_same_path(self) -> None:
        """Same exact path, opposite outcomes, keyed only by the registry —
        proves precedence is deterministic and driven by the registry, not
        by blueprint registration order (both apps register blueprints in
        the same order via register_blueprints)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )
        jinja_app = _app_with_registry(())
        jinja_response = jinja_app.test_client().get("/investigations/")
        assert b"inv-abc123" in jinja_response.data

        # The React half actually serves the built shell (reads dist/index.html),
        # so the request itself only runs when the frontend has been built —
        # skipped in the Python-only CI job. The Jinja half above always runs.
        if _dist_available():
            react_app = _app_with_registry(("/investigations",))
            react_response = react_app.test_client().get("/investigations/")
            react_data = react_response.get_data(as_text=True)
            assert b"inv-abc123" not in react_response.data
            assert (
                "<!doctype html>" in react_data.lower()
                or "<html" in react_data.lower()
            )


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

        response = client.get("/api/v1/investigations/")

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
