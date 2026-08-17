"""Tests for Task 5.3 — BFF JSON API for the React Sources + Spending views.

Acceptance criterion (`[T]`, per docs/design/route-parity-targets.md §4a/§4b):
"Sources status + Spending render at parity (FR34/FR35)".

Each `[T]` half is proven by a dedicated test class below:

[T-Sources]  GET /api/v1/sources  — JSON (not HTML); reuses
             ``SourceService.get_sources()`` verbatim, including its
             dedup-by-name behavior (NFR12); 503 JSON error when the
             operator is unreachable.
[T-Spending] GET /api/v1/spending — JSON (not HTML); includes summary,
             cap_status, provider_config, trend; 503 JSON error on failure;
             and — the security-critical assertion the task calls out
             explicitly — the endpoint NEVER returns the unmasked
             BEEPER_LLM_API_KEY value, only the ``api_key_masked`` suffix
             SpendingService.get_provider_config() already produces.

Follows the same respx/patch-based conventions as
``ui/tests/test_api_v1_investigations.py`` (the Task 1.6 model this task
was told to follow) and reuses the mock source payloads from
``ui/tests/test_sources_spending_views.py`` where useful.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.spending_service import SpendingService

SOURCES_URL = "http://mock-operator:8080/api/v1/sources"


# ---------------------------------------------------------------------------
# [T-Sources] GET /api/v1/sources — JSON list endpoint (FR34)
# ---------------------------------------------------------------------------


class TestSourcesListEndpoint:
    """[T-Sources] /api/v1/sources returns JSON with the expected shape."""

    @respx.mock
    def test_returns_json_content_type(self, client: FlaskClient) -> None:
        """Response Content-Type must be application/json (not text/html)."""
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        }
                    ]
                },
            )
        )
        resp = client.get("/api/v1/sources/")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @respx.mock
    def test_no_html_in_body(self, client: FlaskClient) -> None:
        """Response body contains no HTML markup."""
        respx.get(SOURCES_URL).mock(return_value=Response(200, json={"sources": []}))
        resp = client.get("/api/v1/sources/")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @respx.mock
    def test_returns_array(self, client: FlaskClient) -> None:
        """Response body is a JSON array (mirrors investigations_list_json's contract)."""
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        },
                        {
                            "name": "loki-prod",
                            "type": "loki",
                            "endpoint": "http://loki:3100",
                            "status": "error",
                            "last_check": "2026-05-29T11:00:00Z",
                            "error": {
                                "type": "connection_error",
                                "message": "Connection refused",
                                "details": "dial tcp: connection refused",
                            },
                        },
                    ]
                },
            )
        )
        resp = client.get("/api/v1/sources/")
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 2

    @respx.mock
    def test_element_shape(self, client: FlaskClient) -> None:
        """Each element has the fields the React SourcesPage needs, incl. the nested error."""
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "loki-prod",
                            "type": "loki",
                            "endpoint": "http://loki:3100",
                            "status": "error",
                            "last_check": "2026-05-29T11:00:00Z",
                            "error": {
                                "type": "connection_error",
                                "message": "Connection refused",
                                "details": "dial tcp: connection refused",
                            },
                        }
                    ]
                },
            )
        )
        resp = client.get("/api/v1/sources/")
        elem = resp.get_json()[0]
        assert elem["name"] == "loki-prod"
        assert elem["type"] == "loki"
        assert elem["endpoint"] == "http://loki:3100"
        assert elem["status"] == "error"
        assert elem["last_check"] == "2026-05-29T11:00:00Z"
        assert elem["error"] == {
            "type": "connection_error",
            "message": "Connection refused",
            "details": "dial tcp: connection refused",
        }

    @respx.mock
    def test_element_with_no_error_has_null_error(self, client: FlaskClient) -> None:
        """A healthy source's ``error`` field serializes as JSON null, not omitted/undefined."""
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        }
                    ]
                },
            )
        )
        resp = client.get("/api/v1/sources/")
        elem = resp.get_json()[0]
        assert "error" in elem
        assert elem["error"] is None

    @respx.mock
    def test_dedup_by_name_preserved(self, client: FlaskClient) -> None:
        """NFR12: a duplicate-reported source (e.g. mid-restart resume) appears once.

        Proves the JSON endpoint reuses ``SourceService.get_sources()``
        verbatim rather than re-fetching/re-serializing raw operator JSON —
        the service's own dedup-by-name logic (source_service.py) is what
        this test is really pinning.
        """
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        },
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        },
                    ]
                },
            )
        )
        resp = client.get("/api/v1/sources/")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "prometheus-main"

    @respx.mock
    def test_operator_unavailable_returns_503(self, client: FlaskClient) -> None:
        """Operator connection failure returns a JSON error with 503 (not an HTML page)."""
        import httpx

        respx.get(SOURCES_URL).mock(side_effect=httpx.ConnectError("connection refused"))
        resp = client.get("/api/v1/sources/")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "operator_unavailable"

    @respx.mock
    def test_operator_http_error_returns_503(self, client: FlaskClient) -> None:
        """A non-2xx operator response is surfaced as a 503 JSON error too."""
        respx.get(SOURCES_URL).mock(return_value=Response(500))
        resp = client.get("/api/v1/sources/")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "operator_unavailable"


# ---------------------------------------------------------------------------
# [T-Spending] GET /api/v1/spending — JSON dashboard endpoint (FR35)
# ---------------------------------------------------------------------------


_SUMMARY = {
    "daily_cost_usd": 12.34,
    "monthly_cost_usd": 150.0,
    "daily_cap_usd": 50.0,
    "monthly_cap_usd": 500.0,
    "daily_pct": 24.7,
    "monthly_pct": 30.0,
    "projected_monthly_usd": 200.0,
    "daily_investigation_count": 15,
    "monthly_investigation_count": 200,
    "rate_per_hour": 5,
    "rate_limit": 100,
}

_CAP_STATUS = {
    "enforcement_active": False,
    "caps_configured": True,
    "warnings": [],
}

_PROVIDER_CONFIG = {
    "provider": "anthropic",
    "model": "claude-sonnet-4",
    "endpoint": None,
    "api_key_masked": "••••••1234",
    "api_key_configured": True,
    "configured": True,
    "daily_cap_usd": 50.0,
    "monthly_cap_usd": 500.0,
    "rate_limit": 100,
}

_TREND = [
    {"period": "2026-05-27", "cost_usd": 3.5, "count": 4},
    {"period": "2026-05-28", "cost_usd": 8.84, "count": 9},
]


class TestSpendingJsonEndpoint:
    """[T-Spending] /api/v1/spending returns JSON with summary/cap_status/provider_config/trend."""

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_returns_json_content_type(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        """Content-Type is application/json, not text/html."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = _SUMMARY
        mock_svc.get_cap_status.return_value = _CAP_STATUS
        mock_svc.get_provider_config.return_value = _PROVIDER_CONFIG
        mock_svc.get_spending_trend.return_value = _TREND
        mock_get_svc.return_value = mock_svc

        resp = client.get("/api/v1/spending/")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_no_html_in_body(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        """Response body contains no HTML markup."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = _SUMMARY
        mock_svc.get_cap_status.return_value = _CAP_STATUS
        mock_svc.get_provider_config.return_value = _PROVIDER_CONFIG
        mock_svc.get_spending_trend.return_value = _TREND
        mock_get_svc.return_value = mock_svc

        resp = client.get("/api/v1/spending/")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_response_shape(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        """Response includes summary/cap_status/provider_config/trend (FR35)."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = _SUMMARY
        mock_svc.get_cap_status.return_value = _CAP_STATUS
        mock_svc.get_provider_config.return_value = _PROVIDER_CONFIG
        mock_svc.get_spending_trend.return_value = _TREND
        mock_get_svc.return_value = mock_svc

        resp = client.get("/api/v1/spending/")
        data = resp.get_json()

        assert data["summary"] == _SUMMARY
        assert data["cap_status"] == _CAP_STATUS
        assert data["provider_config"] == _PROVIDER_CONFIG
        assert data["trend"] == _TREND

        # Provider config fields the React view renders (FR35).
        assert data["provider_config"]["provider"] == "anthropic"
        assert data["provider_config"]["model"] == "claude-sonnet-4"
        assert data["provider_config"]["configured"] is True

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_service_closed_on_success(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        """The SpendingService's Qdrant client connection is always closed after the request."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = _SUMMARY
        mock_svc.get_cap_status.return_value = _CAP_STATUS
        mock_svc.get_provider_config.return_value = _PROVIDER_CONFIG
        mock_svc.get_spending_trend.return_value = _TREND
        mock_get_svc.return_value = mock_svc

        client.get("/api/v1/spending/")
        mock_svc.close.assert_called_once()

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_spending_data_unavailable_returns_503(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """A backing-store failure (e.g. Qdrant down) returns a JSON 503 error, not HTML."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.side_effect = RuntimeError("qdrant unreachable")
        mock_get_svc.return_value = mock_svc

        resp = client.get("/api/v1/spending/")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "spending_data_unavailable"
        # Service is still closed even on failure (the route's `finally`).
        mock_svc.close.assert_called_once()

    # ── Security-critical assertion (explicitly required by Task 5.3) ──────

    def test_never_returns_unmasked_api_key(self, client: FlaskClient) -> None:
        """The endpoint NEVER returns the raw BEEPER_LLM_API_KEY value.

        Exercises the REAL ``SpendingService`` (not a mock standing in for
        it) so this actually proves the production masking code path
        (`SpendingService._mask_api_key` / `get_provider_config`) end to
        end through the JSON API — a mocked service returning an
        already-masked value would only prove the route passes data through,
        not that the masking itself happens. Only the Qdrant-backed spend
        aggregation (irrelevant to the API-key assertion) is stubbed out, so
        no real Qdrant connection is required for this test.
        """
        secret_api_key = "sk-live-topsecret-abcd1234"

        with (
            patch.dict(
                "os.environ",
                {
                    "BEEPER_LLM_PROVIDER": "anthropic",
                    "BEEPER_LLM_MODEL": "claude-sonnet-4",
                    "BEEPER_LLM_API_KEY": secret_api_key,
                },
                clear=False,
            ),
            patch.object(
                SpendingService,
                "_scroll_investigations_with_costs",
                return_value=[],
            ),
        ):
            resp = client.get("/api/v1/spending/")

        assert resp.status_code == 200
        raw_body = resp.get_data(as_text=True)

        # The raw secret must never appear anywhere in the response body.
        assert secret_api_key not in raw_body
        assert "topsecret" not in raw_body

        # The masked form (last 4 chars only, per _mask_api_key) IS present.
        data = resp.get_json()
        assert data["provider_config"]["api_key_masked"] == "••••••1234"
        assert data["provider_config"]["api_key_configured"] is True
        assert "1234" in raw_body
