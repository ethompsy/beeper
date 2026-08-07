"""Tests for Task 5.2 — BFF JSON API for the React Ingestion Stats view.

Acceptance criteria (each [T] maps to a clearly-named test class):

[T1] GET /api/v1/ingestion/stats returns JSON (not HTML); Content-Type is
     application/json; the response has all 11 `IngestionStats` fields,
     snake_case, mirroring the operator's own response shape.
[T2] The route reuses HealthService.get_ingestion_stats() — proven by
     asserting it hits the same operator endpoint
     (`/api/v1/ingestion/stats`) the Jinja `/health/ingestion` route uses,
     with no reimplementation of the HTTP call.
[T3] Operator-unavailable failures return a JSON 503 error body (matching
     `investigations_api_bp`'s `operator_unavailable` convention), never an
     HTML error page.
[T4] The existing Jinja `/health/ingestion` route is unchanged by this task
     (still renders HTML, still serves the same template context) — a
     regression guard proving the two blueprints stayed independent.
"""

from __future__ import annotations

import httpx
import respx
from flask.testing import FlaskClient
from httpx import Response

_STATS_RESPONSE = {
    "buffer_size": 10000,
    "buffered_count": 42,
    "dropped_count": 0,
    "is_full": False,
    "metrics_received": 1234,
    "logs_received": 5678,
    "anomalies_detected": 3,
    "anomalies_suppressed": 1,
    "active_metric_detectors": 7,
    "ewma_warmup_samples": 45,
    "ewma_warmup_minimum": 100,
}


class TestIngestionStatsJsonEndpoint:
    """[T1] GET /api/v1/ingestion/stats returns JSON with the full field set."""

    @respx.mock
    def test_returns_json_content_type(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/api/v1/ingestion/stats")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @respx.mock
    def test_no_html_in_body(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/api/v1/ingestion/stats")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @respx.mock
    def test_response_has_all_eleven_fields_snake_case(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/api/v1/ingestion/stats")
        data = resp.get_json()
        assert data == _STATS_RESPONSE

    @respx.mock
    def test_field_values_pass_through_unmodified(self, client: FlaskClient) -> None:
        """No derived pipeline_state/warmup_pct fields — thin passthrough only."""
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/api/v1/ingestion/stats")
        data = resp.get_json()
        assert "pipeline_state" not in data
        assert "warmup_pct" not in data
        assert "is_warming" not in data
        assert data["ewma_warmup_samples"] == 45
        assert data["ewma_warmup_minimum"] == 100
        assert data["metrics_received"] == 1234
        assert data["logs_received"] == 5678
        assert data["anomalies_detected"] == 3
        assert data["anomalies_suppressed"] == 1
        assert data["active_metric_detectors"] == 7

    @respx.mock
    def test_missing_operator_fields_default_via_ingestion_stats_from_dict(
        self, client: FlaskClient
    ) -> None:
        """Reuses IngestionStats.from_dict's own defaulting — no separate defaulting logic here."""
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json={"buffer_size": 10000})
        )
        resp = client.get("/api/v1/ingestion/stats")
        data = resp.get_json()
        assert data["metrics_received"] == 0
        assert data["ewma_warmup_minimum"] == 0
        assert data["is_full"] is False


class TestReusesHealthService:
    """[T2] The route calls through HealthService — same operator endpoint the
    Jinja route reads, no reimplementation of the HTTP call."""

    @respx.mock
    def test_hits_the_same_operator_endpoint_as_jinja_route(self, client: FlaskClient) -> None:
        mock_route = respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )

        client.get("/api/v1/ingestion/stats")

        assert mock_route.called
        assert mock_route.call_count == 1


class TestOperatorUnavailable:
    """[T3] Operator failures return a JSON 503 error, never an HTML error page."""

    @respx.mock
    def test_connect_error_returns_503_json(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        resp = client.get("/api/v1/ingestion/stats")
        assert resp.status_code == 503
        assert "application/json" in resp.content_type
        data = resp.get_json()
        assert data["error"] == "operator_unavailable"

    @respx.mock
    def test_timeout_returns_503_json(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        resp = client.get("/api/v1/ingestion/stats")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "operator_unavailable"

    @respx.mock
    def test_operator_5xx_returns_503_json(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(500)
        )
        resp = client.get("/api/v1/ingestion/stats")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "operator_unavailable"

    def test_error_body_is_valid_json_not_html(self, client: FlaskClient) -> None:
        # No respx mock registered at all → httpx raises a connection error
        # against the (non-existent) mock-operator host, exercising the same
        # except HealthServiceError branch without needing a live server.
        resp = client.get("/api/v1/ingestion/stats")
        assert resp.status_code == 503
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw


class TestJinjaRouteUnchanged:
    """[T4] Regression guard: `/health/ingestion` (Jinja) is untouched by this
    task — still HTML, still the same template context contract."""

    @respx.mock
    def test_jinja_route_still_renders_html(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/health/ingestion")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"Ingestion &amp; Detection" in resp.data or b"Ingestion & Detection" in resp.data

    @respx.mock
    def test_jinja_htmx_partial_still_works(self, client: FlaskClient) -> None:
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        resp = client.get("/health/ingestion", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" not in resp.data

    @respx.mock
    def test_jinja_and_json_routes_are_independently_registered(self, client: FlaskClient) -> None:
        """Both blueprints answer from the same worker without interfering."""
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=_STATS_RESPONSE)
        )
        html_resp = client.get("/health/ingestion")
        json_resp = client.get("/api/v1/ingestion/stats")
        assert "text/html" in html_resp.content_type
        assert "application/json" in json_resp.content_type

    @respx.mock
    def test_jinja_route_still_raises_no_html_error_regression(self, client: FlaskClient) -> None:
        """HealthServiceError on the Jinja route still degrades to its own
        (HTML) error block, unaffected by the new JSON error path."""
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            side_effect=httpx.ConnectError("down")
        )
        resp = client.get("/health/ingestion")
        assert resp.status_code == 200
        assert b"Unable to fetch ingestion stats" in resp.data
