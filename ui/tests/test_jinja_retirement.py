"""Task 6.3 — Retire Jinja for migrated routes (D13/D14).

End-to-end proof, against the REAL production-shaped `REACT_OWNED_PREFIXES`
value (`ui/beeper_ui/config.py`'s `Config.REACT_OWNED_PREFIXES`, exercised
here via the standard `client`/`app` fixtures from `conftest.py` — no custom
registry override), of the task's three `[T]` acceptance criteria:

  AC1  No migrated route is served by Jinja — every prefix in
       `REACT_OWNED_PREFIXES` 302-redirects its bare URL to the `/app/*`
       equivalent.
       -> `TestAC1AllSixMigratedPrefixesRedirect`

  AC2  The retained Jinja remainder still renders — no orphaned
       imports/includes from deleted templates. (The "still renders" half
       for the ten §7 destinations is covered per-route by their own
       existing test suites, e.g. `test_routes.py::TestHealthRoute`,
       `test_cost_insights.py`, `test_slo_routes.py`, `test_topology_routes
       .py`, `test_services.py`, `test_analytics_dashboard.py`,
       `test_executive_report.py`, `test_handoff_routes.py`,
       `test_notification_config_routes.py`, `test_trust_settings_routes
       .py` — none of those were touched by this task and all still pass
       unmodified, which is itself part of the AC2 proof. This file adds
       the complementary half: proving the un-migrated/carved-out
       *sub-routes* that share a URL prefix with a migrated route are NOT
       swept up by the redirect.)
       -> `TestAC2UnmigratedSubRoutesSurvive`, plus
          `test_no_orphaned_template_includes_after_deletion` below.

  AC3  Redirects are covered by route tests: bare URL -> 302 -> `/app/*` ->
       correct React view (including query-string/FR53-permalink
       preservation).
       -> `TestAC3RedirectChainReachesCorrectReactView`,
          `TestAC3QueryStringPreservation`

See `ui/beeper_ui/routes/react_registry.py` for the redirect mechanism
itself (exclusion patterns, target overrides) and
`ui/tests/test_react_route_registry.py` for its lower-level unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask.testing import FlaskClient

_TESTS_DIR = Path(__file__).parent
_TEMPLATES_DIR = _TESTS_DIR.parent / "beeper_ui" / "templates"
_DIST = _TESTS_DIR.parent / "frontend" / "dist"

_DIST_MISSING_REASON = (
    f"frontend dist not built: run `npm run build` in ui/frontend/ first. "
    f"(looked for {_DIST})"
)


def _dist_available() -> bool:
    return (_DIST / "index.html").is_file()


# ---------------------------------------------------------------------------
# AC1 — every REACT_OWNED_PREFIXES entry 302-redirects its bare URL
# ---------------------------------------------------------------------------


class TestAC1AllSixMigratedPrefixesRedirect:
    """Every migrated route 302-redirects to its `/app/*` equivalent."""

    @pytest.mark.parametrize(
        ("bare_url", "expected_location"),
        [
            ("/investigations/", "/app/investigations"),
            ("/investigations", "/app/investigations"),
            ("/investigations/inv-abc123", "/app/investigations/inv-abc123"),
            ("/knowledge/", "/app/knowledge"),
            ("/knowledge/kb-entry-42", "/app/knowledge/kb-entry-42"),
            ("/knowledge/search", "/app/knowledge"),
            ("/health/ingestion", "/app/ingestion-stats"),
            ("/sources/", "/app/sources"),
            ("/spending/", "/app/spending"),
            ("/spending/status", "/app/spending"),
            ("/metrics/", "/app/metrics"),
            ("/metrics/mttr", "/app/metrics"),
            ("/metrics/mttr/drilldown", "/app/metrics"),
        ],
    )
    def test_bare_url_redirects_to_app_equivalent(
        self, client: FlaskClient, bare_url: str, expected_location: str
    ) -> None:
        response = client.get(bare_url)
        assert response.status_code == 302, (
            f"{bare_url} did not redirect (got {response.status_code}) — "
            "expected it to still be React-owned"
        )
        assert response.headers["Location"] == expected_location

    def test_htmx_header_does_not_prevent_redirect(self, client: FlaskClient) -> None:
        """The old dual-mode (full page vs. HX-Request partial) branches are
        gone — an HX-Request header no longer changes anything for a
        migrated route; it still redirects."""
        response = client.get("/spending/", headers={"HX-Request": "true"})
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/spending"

    def test_all_six_prefixes_from_config_are_covered_above(self) -> None:
        """Guard: keeps this file's parametrized URL list honest against the
        real `REACT_OWNED_PREFIXES` value if it's ever edited."""
        from beeper_ui.config import Config

        assert set(Config.REACT_OWNED_PREFIXES) == {
            "/investigations",
            "/knowledge",
            "/health/ingestion",
            "/sources",
            "/spending",
            "/metrics",
        }


# ---------------------------------------------------------------------------
# AC2 — un-migrated / carved-out sub-routes are NOT swept up by the redirect
# ---------------------------------------------------------------------------


class TestAC2UnmigratedSubRoutesSurvive:
    """Routes that share a URL prefix with a migrated route, but are
    explicitly NOT migrated (route-parity-targets.md carve-outs), still
    dispatch to their real Jinja view — proven by asserting they do NOT
    302-redirect (a 405/404/500/200 from the real view is all acceptable
    here; a 302 to `/app/*` would mean the exclusion regex regressed)."""

    @pytest.mark.parametrize(
        "url",
        [
            # Cost Insights — a separate, un-migrated nav destination that
            # happens to share the `/spending` prefix (route-parity-
            # targets.md §7).
            "/spending/costs",
            "/spending/costs/breakdown",
            "/spending/costs/export",
            # Knowledge write/history/admin routes (route-parity-
            # targets.md §2 carve-outs).
            "/knowledge/import",
            "/knowledge/learning",
            "/knowledge/learning/adjustments",
            "/knowledge/trust-settings",
            "/knowledge/services/payments/knowledge",
            "/knowledge/api/learning/prompt-context/payments",
            # Metrics CSV/JSON export (no template; React links to it).
            "/metrics/export",
            # Health: the general overview + the UI's own health check are
            # separate routes from the migrated `/health/ingestion`.
            "/health/",
            "/health/api",
        ],
    )
    def test_carved_out_route_does_not_redirect(
        self, client: FlaskClient, url: str
    ) -> None:
        response = client.get(url)
        assert response.status_code != 302, (
            f"{url} was redirected — it should be an explicit carve-out "
            "excluded from the React registry (react_registry.py "
            "_REDIRECT_EXCLUSION_PATTERNS), not swept up with its migrated "
            "sibling prefix"
        )

    @pytest.mark.parametrize(
        "entry_id_suffixed_url",
        [
            # Dynamic-segment knowledge carve-outs: `<entry_id>` varies, so
            # these can't be excluded by a literal string — proves the
            # regex-based exclusion handles a real (fake) id correctly.
            "/knowledge/kb-42/edit",
            "/knowledge/kb-42/history",
            "/knowledge/kb-42/related",
            "/knowledge/kb-42/corrections",
            "/knowledge/kb-42/corrections/panel",
        ],
    )
    def test_dynamic_knowledge_carve_out_does_not_redirect(
        self, client: FlaskClient, entry_id_suffixed_url: str
    ) -> None:
        response = client.get(entry_id_suffixed_url)
        assert response.status_code != 302

    def test_investigation_action_routes_do_not_redirect(
        self, client: FlaskClient
    ) -> None:
        """The Jinja-only, `require_role`-gated investigation action routes
        (verify/confirm/reject/resolve/feedback/related-kb/linked-kb/
        gate-status/urgency/remediation-progress) and both HTML SSE streams
        were never called by React and are deliberately preserved, not
        migrated — GET-able ones return real content (200), not a redirect.
        """
        for suffix in (
            "related-kb",
            "linked-kb",
            "gate-status",
            "urgency",
            "remediation-progress",
        ):
            response = client.get(f"/investigations/inv-1/{suffix}")
            assert response.status_code != 302, f"/investigations/inv-1/{suffix}"

    def test_path_traversal_shaped_id_does_not_redirect(
        self, client: FlaskClient
    ) -> None:
        """A `..`-laden path never matches the registry (see
        `react_registry.py`'s `_is_always_excluded`) — it falls through to
        Flask's normal dispatch/404 exactly as it did before Task 6.3,
        instead of getting redirected to an equally malformed `/app/...`
        URL. Found during test migration: Werkzeug's test client (and some
        raw HTTP clients) pass `..` segments straight through unnormalized,
        so this was a real, if low-severity, behavior regression risk.
        """
        response = client.get("/investigations/../../etc/passwd")
        assert response.status_code == 404
        assert response.status_code != 302

        response = client.post("/investigations/../../etc/passwd/confirm", data={})
        assert response.status_code == 404
        assert response.status_code != 302

    def test_investigation_detail_stream_is_excluded_from_redirect(self) -> None:
        """`/investigations/<id>/stream` (the per-investigation HTML SSE) is
        excluded from the redirect. Checked at the registry-predicate level,
        not via a live `client.get()` — that route's view function is an
        infinite polling generator (`_generate_detail_sse_events`), and the
        Flask test client eagerly drains a response's iterable, so a
        blocking `client.get()` on it would hang the test suite rather than
        return; `test_sse_streaming.py` covers its real behavior via the
        generator function directly, not full HTTP round-trips.
        """
        from beeper_ui.config import Config
        from beeper_ui.routes.react_registry import (
            _is_redirect_excluded,
            matches_react_prefix,
        )

        path = "/investigations/inv-1/stream"
        assert matches_react_prefix(path, Config.REACT_OWNED_PREFIXES)
        assert _is_redirect_excluded(path)


def test_no_orphaned_template_includes_after_deletion() -> None:
    """AC2's "no orphaned imports/includes" half: every `{% include %}` /
    `{% from ... import %}` reference anywhere in the retained template
    tree must resolve to a file that still exists on disk. Catches the
    exact failure mode of deleting a template that something else still
    references.
    """
    import re

    include_re = re.compile(r'{%-?\s*(?:include|from)\s+["\']([^"\']+\.html)["\']')
    problems: list[str] = []
    for path in _TEMPLATES_DIR.rglob("*.html"):
        text = path.read_text()
        for referenced in include_re.findall(text):
            if not (_TEMPLATES_DIR / referenced).is_file():
                problems.append(f"{path.relative_to(_TEMPLATES_DIR)} -> {referenced}")
    assert not problems, f"orphaned template include(s) found: {problems}"


# ---------------------------------------------------------------------------
# AC3 — redirect chain: bare URL -> 302 -> /app/* -> correct React view
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
class TestAC3RedirectChainReachesCorrectReactView:
    """Follows the redirect end-to-end and confirms it lands on the built
    React SPA shell (which owns client-side routing to the correct view) —
    not a 404, not a bare index with no matching route.
    """

    @pytest.mark.parametrize(
        "bare_url",
        [
            "/investigations/",
            "/investigations/inv-abc123",
            "/knowledge/",
            "/knowledge/kb-entry-42",
            "/knowledge/search",
            "/health/ingestion",
            "/sources/",
            "/spending/",
            "/spending/status",
            "/metrics/",
            "/metrics/mttr",
        ],
    )
    def test_following_redirect_reaches_spa_shell(
        self, client: FlaskClient, bare_url: str
    ) -> None:
        response = client.get(bare_url, follow_redirects=True)
        assert response.status_code == 200
        data = response.get_data(as_text=True)
        assert "<!doctype html>" in data.lower() or "<html" in data.lower()
        # The shell mounts React Router at /app (basename) — confirms this
        # is genuinely the SPA shell, not some other 200 response.
        assert '<div id="root">' in data


# ---------------------------------------------------------------------------
# AC3 — query-string (FR53 permalink) preservation across the redirect
# ---------------------------------------------------------------------------


class TestAC3QueryStringPreservation:
    """FR53: every migrated view's URL-encoded filter/search state must
    round-trip through the redirect — a redirect that silently drops the
    query string would break permalinks on first load.
    """

    def test_knowledge_search_query_preserved(self, client: FlaskClient) -> None:
        response = client.get("/knowledge/?q=disk+space")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/knowledge?q=disk+space"

    def test_knowledge_search_route_query_preserved(self, client: FlaskClient) -> None:
        # /knowledge/search itself target-overrides to /app/knowledge — the
        # query string must still survive that remap.
        response = client.get("/knowledge/search?q=timeout&entry_type=runbook")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/knowledge?q=timeout&entry_type=runbook"

    def test_investigations_status_group_query_preserved(
        self, client: FlaskClient
    ) -> None:
        response = client.get("/investigations/?status_group=resolved")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/investigations?status_group=resolved"

    def test_metrics_filter_query_preserved(self, client: FlaskClient) -> None:
        response = client.get("/metrics/?period=quarter&service=payments&severity=high")
        assert response.status_code == 302
        assert (
            response.headers["Location"]
            == "/app/metrics?period=quarter&service=payments&severity=high"
        )

    def test_metrics_mttr_alias_query_preserved_through_override(
        self, client: FlaskClient
    ) -> None:
        # /metrics/mttr target-overrides to /app/metrics — query must survive.
        response = client.get("/metrics/mttr?period=week")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/metrics?period=week"

    def test_multi_value_query_string_preserved_verbatim(
        self, client: FlaskClient
    ) -> None:
        response = client.get("/sources/?foo=1&foo=2&bar=baz")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/sources?foo=1&foo=2&bar=baz"

    def test_no_query_string_no_trailing_question_mark(
        self, client: FlaskClient
    ) -> None:
        response = client.get("/sources/")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/sources"
        assert "?" not in response.headers["Location"]
