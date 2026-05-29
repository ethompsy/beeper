"""Tests for Task 5.3 — Source connection status & LLM spending views.

One named test per acceptance criterion:

- AC1 (FR34): Observe > Sources shows Prometheus/Loki connection status with
  indicators.
- AC2:        Connected → green "Connected" + last-seen; disconnected/error →
  red "Disconnected".
- AC3 (FR35): Manage > Spending shows LLM provider config + spending metrics.
- AC4 (NFR12): After a simulated operator restart, the Sources view renders a
  consistent, duplicate-free list (UI-layer surface of the operator's
  idempotent CRD resume guarantee).

These follow the project test convention (render assertions via the Flask test
client; no JS runner). Source data is mocked at the operator HTTP boundary with
respx; spending provider config is exercised through the SpendingService and
the spending route template.
"""

from unittest.mock import MagicMock, patch

import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.spending_service import SpendingService

SOURCES_URL = "http://mock-operator:8080/api/v1/sources"


# ── AC1 ──────────────────────────────────────────────────────────────────────


class TestAC1SourceConnectionStatusIndicators:
    """AC1 (FR34): Sources view shows Prometheus/Loki status with indicators."""

    @respx.mock
    def test_ac1_sources_show_prometheus_loki_status_indicators(
        self, client: FlaskClient
    ) -> None:
        """Both Prometheus and Loki sources render with a status indicator."""
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
                            "status": "connected",
                            "last_check": "2026-05-29T12:00:00Z",
                            "error": None,
                        },
                    ]
                },
            )
        )

        response = client.get("/sources/")
        body = response.data.decode()

        assert response.status_code == 200
        # Both source types are listed.
        assert "prometheus-main" in body
        assert "loki-prod" in body
        assert "prometheus" in body
        assert "loki" in body
        # A status indicator badge renders per source (status_badge macro
        # emits data-status + the colored dot span).
        assert body.count('class="status-badge') >= 2
        assert 'data-status="connected"' in body


# ── AC2 ──────────────────────────────────────────────────────────────────────


class TestAC2ConnectedDisconnectedIndicators:
    """AC2: connected → green Connected + last-seen; error → red Disconnected."""

    @respx.mock
    def test_ac2_connected_green_with_last_seen_disconnected_red(
        self, client: FlaskClient
    ) -> None:
        """Connected source is green w/ last-seen; errored source is red."""
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
                            "last_check": "2026-05-29T12:34:00Z",
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

        response = client.get("/sources/")
        body = response.data.decode()

        assert response.status_code == 200

        # Connected → green token + "Connected" label + last-seen timestamp.
        assert "Connected" in body
        assert "text-status-healthy" in body
        assert "2026-05-29T12:34:00Z" in body  # last-seen for connected source

        # Disconnected (operator reports "error") → red token + "Disconnected".
        assert "Disconnected" in body
        assert "text-status-critical" in body
        assert "Connection refused" in body

    @respx.mock
    def test_ac2_disconnected_source_renders_red_label(
        self, client: FlaskClient
    ) -> None:
        """A source reporting 'disconnected' maps to the red Disconnected badge."""
        respx.get(SOURCES_URL).mock(
            return_value=Response(
                200,
                json={
                    "sources": [
                        {
                            "name": "prometheus-main",
                            "type": "prometheus",
                            "endpoint": "http://prometheus:9090",
                            "status": "disconnected",
                            "last_check": "2026-05-29T10:00:00Z",
                            "error": None,
                        }
                    ]
                },
            )
        )

        body = client.get("/sources/").data.decode()
        assert "Disconnected" in body
        assert "text-status-critical" in body


# ── AC3 ──────────────────────────────────────────────────────────────────────


class TestAC3SpendingProviderConfigAndMetrics:
    """AC3 (FR35): Spending shows LLM provider config + spending metrics."""

    def test_ac3_provider_config_masks_api_key_and_reads_env(self) -> None:
        """get_provider_config surfaces provider/model and masks the API key."""
        svc = SpendingService()
        with patch.dict(
            "os.environ",
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "sk-secret-abcd1234",
                "BEEPER_LLM_DAILY_CAP_CENTS": "5000",
            },
            clear=False,
        ):
            cfg = svc.get_provider_config()

        assert cfg["configured"] is True
        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-sonnet-4"
        assert cfg["daily_cap_usd"] == 50.0
        # API key is masked — never returned in full.
        assert cfg["api_key_configured"] is True
        assert cfg["api_key_masked"] == "••••••1234"
        assert "sk-secret-abcd1234" not in str(cfg["api_key_masked"])

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_ac3_spending_dashboard_shows_provider_config_and_metrics(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Spending page renders the provider config block + spend metrics."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = {
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
        mock_svc.get_cap_status.return_value = {
            "enforcement_active": False,
            "caps_configured": True,
            "warnings": [],
        }
        mock_svc.get_provider_config.return_value = {
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
        mock_svc.get_spending_trend.return_value = []
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/")
        body = response.data.decode()

        assert response.status_code == 200
        # Provider config (FR35).
        assert "LLM Provider Configuration" in body
        assert "anthropic" in body
        assert "claude-sonnet-4" in body
        assert "••••••1234" in body
        # Spending metrics.
        assert "12.34" in body  # daily spend
        assert "150.00" in body  # monthly spend
        assert "Daily Spend" in body
        assert "Monthly Spend" in body


# ── AC4 / NFR12 ───────────────────────────────────────────────────────────────


class TestAC4RestartStateConsistency:
    """AC4 (NFR12): operator restart resumes CRDs without duplicates.

    The operator-level guarantee (deterministic Job names so a restart resumes
    the same Investigation CRDs idempotently) is verified in the Rust operator
    tests (Story 2.1: test_deterministic_job_name_prevents_duplicates). Here we
    assert the UI-facing consistency property: given the post-restart service
    state the Sources view reads, the rendered list is stable and duplicate
    free — a restart that re-reconciles the same CRDs must not surface ghost or
    doubled source rows.
    """

    @respx.mock
    def test_ac4_sources_view_is_consistent_and_dedup_free_after_restart(
        self, client: FlaskClient
    ) -> None:
        """Two reads across a simulated restart yield identical, dedup-free lists."""
        # State the operator returns BEFORE and AFTER a restart. Because the
        # operator resumes the same CRDs idempotently, the source set is
        # identical across the restart boundary.
        steady_state = {
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
                    "status": "connected",
                    "last_check": "2026-05-29T12:00:00Z",
                    "error": None,
                },
            ]
        }

        route = respx.get(SOURCES_URL)
        # First call = pre-restart, second call = post-restart resume.
        route.side_effect = [
            Response(200, json=steady_state),
            Response(200, json=steady_state),
        ]

        before = client.get("/sources/").data.decode()
        after = client.get("/sources/").data.decode()

        # Consistency: the view is byte-stable across the restart boundary.
        assert before == after
        # No duplicate source rows surfaced by the resume (each name once).
        assert after.count("prometheus-main") == 1
        assert after.count("loki-prod") == 1

    @respx.mock
    def test_ac4_duplicate_resume_payload_is_deduplicated_by_name(
        self, client: FlaskClient
    ) -> None:
        """Defensive: even if a resume momentarily double-reports a CRD, the
        Sources list de-duplicates by name so no doubled row reaches the user.
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

        body = client.get("/sources/").data.decode()
        # The duplicate CRD appears exactly once in the rendered list.
        assert body.count("prometheus-main") == 1
