"""Unit tests for HandoffService."""

from datetime import datetime, timezone

import httpx
import respx
from httpx import Response

from beeper_ui.services.handoff_service import (
    HandoffService,
    HandoffSummary,
)

MOCK_OPERATOR_URL = "http://mock-operator:8080"


# -----------------------------------------------------------------
# Fixtures / helper data
# -----------------------------------------------------------------

def _make_investigation(
    id: str,
    status: str,
    service: str = "api-svc",
    severity: str = "medium",
    condition: str = "degraded",
    started_at: str = "2026-03-16T08:00:00+00:00",
    completed_at: str | None = None,
    triggered_at: str | None = None,
) -> dict:
    return {
        "id": id,
        "status": status,
        "service": service,
        "severity": severity,
        "condition": condition,
        "started_at": started_at,
        "completed_at": completed_at,
        "triggered_at": triggered_at,
    }


def _make_slo_service(
    name: str,
    condition: str = "healthy",
    compliance: float = 0.999,
    burn_rate: float = 0.5,
) -> dict:
    return {
        "name": name,
        "condition": condition,
        "compliance": compliance,
        "burn_rate": burn_rate,
    }


def _recent_iso() -> str:
    """ISO timestamp ~1 hour ago (within the 8-hour window)."""
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def _old_iso() -> str:
    """ISO timestamp ~10 hours ago (outside the 8-hour window)."""
    from datetime import timedelta

    return (
        datetime.now(timezone.utc) - timedelta(hours=10)
    ).replace(microsecond=0).isoformat()


# -----------------------------------------------------------------
# HandoffSummary dataclass
# -----------------------------------------------------------------

class TestHandoffSummary:
    """Tests for HandoffSummary dataclass."""

    def test_defaults(self) -> None:
        s = HandoffSummary()
        assert s.active_investigations == []
        assert s.resolved_incidents == []
        assert s.slo_status == []
        assert s.items_to_watch == []
        assert s.generated_at == ""
        assert s.is_all_clear is False

    def test_to_dict(self) -> None:
        s = HandoffSummary(
            active_investigations=[{"id": "inv-1"}],
            resolved_incidents=[],
            slo_status=[{"name": "svc"}],
            items_to_watch=[],
            generated_at="2026-03-16T12:00:00+00:00",
            is_all_clear=False,
        )
        d = s.to_dict()
        assert d["active_investigations"] == [{"id": "inv-1"}]
        assert d["generated_at"] == "2026-03-16T12:00:00+00:00"
        assert d["is_all_clear"] is False

    def test_is_all_clear_flag(self) -> None:
        s = HandoffSummary(is_all_clear=True)
        assert s.to_dict()["is_all_clear"] is True


# -----------------------------------------------------------------
# generate_summary — happy path
# -----------------------------------------------------------------

class TestGenerateSummary:
    """Tests for HandoffService.generate_summary()."""

    @respx.mock
    def test_full_summary_with_mixed_investigations(self) -> None:
        """Active + resolved investigations + SLO data → full summary."""
        recent = _recent_iso()
        old = _old_iso()
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            return_value=Response(
                200,
                json=[
                    _make_investigation("inv-1", "investigating", "auth-svc"),
                    _make_investigation(
                        "inv-2",
                        "completed",
                        "order-svc",
                        completed_at=recent,
                    ),
                    _make_investigation(
                        "inv-3",
                        "completed",
                        "pay-svc",
                        completed_at=old,
                    ),
                ],
            )
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(
                200,
                json={
                    "service_levels": [
                        _make_slo_service("auth-slo", "warning", 0.98, 3.0),
                        _make_slo_service("pay-slo", "healthy", 0.999, 0.3),
                    ]
                },
            )
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert len(summary.active_investigations) == 1
            assert summary.active_investigations[0]["id"] == "inv-1"
            # Only inv-2 is within 8h window
            assert len(summary.resolved_incidents) == 1
            assert summary.resolved_incidents[0]["id"] == "inv-2"
            assert len(summary.slo_status) == 2
            assert summary.is_all_clear is False
            assert summary.generated_at  # non-empty
            # auth-slo warning should be in items_to_watch
            watch_descs = [i["description"] for i in summary.items_to_watch]
            assert any("auth-slo" in d for d in watch_descs)
        finally:
            svc.close()

    @respx.mock
    def test_all_clear_no_active_no_resolved(self) -> None:
        """No active, no recently resolved → is_all_clear."""
        old = _old_iso()
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            return_value=Response(
                200,
                json=[
                    _make_investigation(
                        "inv-old", "completed", completed_at=old
                    ),
                ],
            )
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(
                200, json={"service_levels": [_make_slo_service("x")]}
            )
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert summary.is_all_clear is True
            assert len(summary.active_investigations) == 0
            assert len(summary.resolved_incidents) == 0
        finally:
            svc.close()

    @respx.mock
    def test_all_clear_empty_investigations(self) -> None:
        """Zero investigations → is_all_clear."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert summary.is_all_clear is True
        finally:
            svc.close()


# -----------------------------------------------------------------
# _build_active_investigations
# -----------------------------------------------------------------

class TestBuildActiveInvestigations:
    """Tests for HandoffService._build_active_investigations."""

    def test_filters_active_statuses(self) -> None:
        from beeper_ui.services.investigation_service import Investigation

        investigations = [
            Investigation("a", "investigating", "svc-a", "high", "deg"),
            Investigation("b", "awaiting_confirmation", "svc-b", "low", "ok"),
            Investigation("c", "completed", "svc-c", "med", "ok"),
            Investigation("d", "failed", "svc-d", "low", "err"),
        ]
        result = HandoffService._build_active_investigations(investigations)
        ids = [r["id"] for r in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" not in ids
        assert "d" not in ids

    def test_link_generation(self) -> None:
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation("test-id", "investigating", "s", "h", "c")
        result = HandoffService._build_active_investigations([inv])
        assert result[0]["link"] == "/investigations/test-id"


# -----------------------------------------------------------------
# _build_resolved_incidents
# -----------------------------------------------------------------

class TestBuildResolvedIncidents:
    """Tests for HandoffService._build_resolved_incidents."""

    def test_eight_hour_cutoff(self) -> None:
        from beeper_ui.services.investigation_service import Investigation

        recent = _recent_iso()
        old = _old_iso()
        now = datetime.now(timezone.utc)

        investigations = [
            Investigation(
                "recent", "completed", "s", "m", "c",
                completed_at=recent,
            ),
            Investigation(
                "old", "completed", "s", "m", "c",
                completed_at=old,
            ),
        ]
        result = HandoffService._build_resolved_incidents(investigations, now)
        ids = [r["id"] for r in result]
        assert "recent" in ids
        assert "old" not in ids

    def test_sorted_most_recent_first(self) -> None:
        from datetime import timedelta

        from beeper_ui.services.investigation_service import Investigation

        now = datetime.now(timezone.utc)
        t1 = (now - timedelta(hours=2)).isoformat()
        t2 = (now - timedelta(hours=1)).isoformat()

        investigations = [
            Investigation("older", "completed", "s", "m", "c", completed_at=t1),
            Investigation("newer", "completed", "s", "m", "c", completed_at=t2),
        ]
        result = HandoffService._build_resolved_incidents(investigations, now)
        assert result[0]["id"] == "newer"
        assert result[1]["id"] == "older"

    def test_excludes_non_completed(self) -> None:
        from beeper_ui.services.investigation_service import Investigation

        now = datetime.now(timezone.utc)
        investigations = [
            Investigation("active", "investigating", "s", "m", "c"),
        ]
        result = HandoffService._build_resolved_incidents(investigations, now)
        assert len(result) == 0

    def test_link_generation(self) -> None:
        from beeper_ui.services.investigation_service import Investigation

        now = datetime.now(timezone.utc)
        recent = _recent_iso()
        investigations = [
            Investigation("x", "completed", "s", "m", "c", completed_at=recent),
        ]
        result = HandoffService._build_resolved_incidents(investigations, now)
        assert result[0]["link"] == "/investigations/x"


# -----------------------------------------------------------------
# _build_slo_status
# -----------------------------------------------------------------

class TestBuildSloStatus:
    """Tests for HandoffService._build_slo_status."""

    def test_maps_service_data(self) -> None:
        services = [_make_slo_service("my-slo", "healthy", 0.999, 0.5)]
        result = HandoffService._build_slo_status(services)
        assert len(result) == 1
        assert result[0]["name"] == "my-slo"
        assert result[0]["condition"] == "healthy"
        assert result[0]["compliance"] == 0.999
        assert result[0]["burn_rate"] == 0.5
        assert result[0]["link"] == "/slo/services/my-slo"

    def test_empty_services(self) -> None:
        assert HandoffService._build_slo_status([]) == []


# -----------------------------------------------------------------
# _build_items_to_watch
# -----------------------------------------------------------------

class TestBuildItemsToWatch:
    """Tests for HandoffService._build_items_to_watch."""

    def test_warning_critical_included(self) -> None:
        services = [
            _make_slo_service("warn-svc", "warning"),
            _make_slo_service("crit-svc", "critical"),
            _make_slo_service("ok-svc", "healthy"),
        ]
        result = HandoffService._build_items_to_watch(services, [])
        descs = [i["description"] for i in result]
        assert any("warn-svc" in d for d in descs)
        assert any("crit-svc" in d for d in descs)
        assert not any("ok-svc" in d for d in descs)

    def test_elevated_burn_rate_included(self) -> None:
        services = [_make_slo_service("hot-svc", "healthy", 0.99, 1.5)]
        result = HandoffService._build_items_to_watch(services, [])
        assert len(result) == 1
        assert "burn rate" in result[0]["description"]
        assert result[0]["type"] == "slo"

    def test_awaiting_confirmation_included(self) -> None:
        active = [
            {
                "id": "inv-1",
                "service": "auth-svc",
                "severity": "high",
                "status": "awaiting_confirmation",
                "link": "/investigations/inv-1",
            }
        ]
        result = HandoffService._build_items_to_watch([], active)
        assert len(result) == 1
        assert result[0]["type"] == "investigation"

    def test_healthy_services_excluded(self) -> None:
        services = [_make_slo_service("ok-svc", "healthy", 0.999, 0.5)]
        result = HandoffService._build_items_to_watch(services, [])
        assert len(result) == 0


# -----------------------------------------------------------------
# Graceful degradation
# -----------------------------------------------------------------

class TestGracefulDegradation:
    """Tests for service failure isolation."""

    @respx.mock
    def test_investigation_failure_still_returns_slo(self) -> None:
        """InvestigationService failure → empty investigations, SLO still present."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(
                200,
                json={"service_levels": [_make_slo_service("x")]},
            )
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert len(summary.active_investigations) == 0
            assert len(summary.resolved_incidents) == 0
            assert len(summary.slo_status) == 1
        finally:
            svc.close()

    @respx.mock
    def test_slo_failure_still_returns_investigations(self) -> None:
        """SloService failure → empty SLO, investigations still present."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            return_value=Response(
                200,
                json=[_make_investigation("inv-1", "investigating")],
            )
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert len(summary.active_investigations) == 1
            assert len(summary.slo_status) == 0
        finally:
            svc.close()

    @respx.mock
    def test_both_fail_returns_empty_summary(self) -> None:
        """Both services fail → empty summary, no crash."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        svc = HandoffService(MOCK_OPERATOR_URL)
        try:
            summary = svc.generate_summary()
            assert len(summary.active_investigations) == 0
            assert len(summary.slo_status) == 0
            assert summary.is_all_clear is True
        finally:
            svc.close()
