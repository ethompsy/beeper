"""Unit tests for SLO service."""

import httpx
import pytest
import respx
from httpx import Response

from beeper_ui.services.slo_service import (
    SloService,
    SloServiceError,
    condition_css_class,
    format_budget_remaining,
    format_burn_rate,
    format_compliance,
    format_projected_exhaustion,
)

MOCK_OPERATOR_URL = "http://mock-operator:8080"

MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {
            "name": "payments-slo",
            "service": "payment-service",
            "sli_type": "availability",
            "target": 0.999,
            "window": "30d",
            "condition": "healthy",
            "compliance": 0.9995,
            "burn_rate": 0.5,
            "error_budget_remaining": 0.85,
            "is_frozen": False,
        },
        {
            "name": "api-slo",
            "service": "api-gateway",
            "sli_type": "latency",
            "target": 0.99,
            "window": "7d",
            "condition": "warning",
            "compliance": 0.985,
            "burn_rate": 3.2,
            "error_budget_remaining": 0.25,
            "is_frozen": True,
        },
    ]
}

MOCK_SERVICE_DETAIL = {
    "name": "payments-slo",
    "service": "payment-service",
    "sli": {
        "type": "availability",
        "metric": "http_requests_total",
        "good_selector": '{code=~"2.."}',
        "total_selector": "{}",
    },
    "objective": {"target": 0.999, "window": "30d"},
    "burn_rate_alerts": [
        {
            "severity": "critical",
            "short_window": "5m",
            "long_window": "1h",
            "factor": 14.4,
        }
    ],
    "condition": "healthy",
    "compliance": 0.9995,
    "burn_rate": 0.5,
    "error_budget_remaining": 0.85,
    "is_frozen": False,
}

MOCK_BUDGET = {
    "name": "payments-slo",
    "service": "payment-service",
    "target": 0.999,
    "error_budget_total": 0.001,
    "error_budget_remaining": 0.85,
    "error_budget_consumed": 0.15,
    "burn_rate": 0.5,
    "projected_exhaustion_secs": 259200.0,
    "is_frozen": False,
    "triggered_policies": [],
}


class TestSloServiceGetServices:
    """Tests for SloService.get_services()."""

    @respx.mock
    def test_get_services_success(self) -> None:
        """Test successful service list retrieval."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(200, json=MOCK_SERVICE_LEVELS)
        )
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_services()
            assert len(result) == 2
            assert result[0]["name"] == "payments-slo"
            assert result[1]["name"] == "api-slo"
        finally:
            svc.close()

    @respx.mock
    def test_get_services_empty(self) -> None:
        """Test empty service list."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_services()
            assert result == []
        finally:
            svc.close()

    @respx.mock
    def test_get_services_api_error(self) -> None:
        """Test connection error raises SloServiceError."""
        respx.get(f"{MOCK_OPERATOR_URL}/api/v1/slo/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            with pytest.raises(SloServiceError, match="Failed to connect"):
                svc.get_services()
        finally:
            svc.close()


class TestSloServiceGetDetail:
    """Tests for SloService.get_service_detail()."""

    @respx.mock
    def test_get_service_detail_success(self) -> None:
        """Test successful service detail retrieval."""
        respx.get(
            f"{MOCK_OPERATOR_URL}/api/v1/slo/services/payments-slo"
        ).mock(return_value=Response(200, json=MOCK_SERVICE_DETAIL))
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_service_detail("payments-slo")
            assert result is not None
            assert result["name"] == "payments-slo"
            assert result["condition"] == "healthy"
        finally:
            svc.close()

    @respx.mock
    def test_get_service_detail_not_found(self) -> None:
        """Test 404 returns None."""
        respx.get(
            f"{MOCK_OPERATOR_URL}/api/v1/slo/services/nonexistent"
        ).mock(return_value=Response(404, json={"error": "not found"}))
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_service_detail("nonexistent")
            assert result is None
        finally:
            svc.close()


class TestSloServiceGetBudget:
    """Tests for SloService.get_service_budget()."""

    @respx.mock
    def test_get_service_budget_success(self) -> None:
        """Test successful budget retrieval."""
        respx.get(
            f"{MOCK_OPERATOR_URL}/api/v1/slo/services/payments-slo/budget"
        ).mock(return_value=Response(200, json=MOCK_BUDGET))
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_service_budget("payments-slo")
            assert result is not None
            assert result["error_budget_remaining"] == 0.85
            assert result["is_frozen"] is False
        finally:
            svc.close()

    @respx.mock
    def test_get_service_budget_not_found(self) -> None:
        """Test 404 returns None."""
        respx.get(
            f"{MOCK_OPERATOR_URL}/api/v1/slo/services/nonexistent/budget"
        ).mock(return_value=Response(404, json={"error": "not found"}))
        svc = SloService(MOCK_OPERATOR_URL)
        try:
            result = svc.get_service_budget("nonexistent")
            assert result is None
        finally:
            svc.close()


class TestFormatCompliance:
    """Tests for format_compliance helper."""

    def test_normal_value(self) -> None:
        assert format_compliance(0.999) == "99.90%"

    def test_full_value(self) -> None:
        assert format_compliance(1.0) == "100.00%"

    def test_zero_value(self) -> None:
        assert format_compliance(0.0) == "0.00%"

    def test_none_value(self) -> None:
        assert format_compliance(None) == "N/A"


class TestFormatBurnRate:
    """Tests for format_burn_rate helper."""

    def test_normal_value(self) -> None:
        assert format_burn_rate(5.2) == "5.2x"

    def test_zero_value(self) -> None:
        assert format_burn_rate(0.0) == "0.0x"

    def test_none_value(self) -> None:
        assert format_burn_rate(None) == "N/A"


class TestFormatBudgetRemaining:
    """Tests for format_budget_remaining helper."""

    def test_normal_value(self) -> None:
        assert format_budget_remaining(0.75) == "75.0%"

    def test_zero_value(self) -> None:
        assert format_budget_remaining(0.0) == "0.0%"

    def test_full_value(self) -> None:
        assert format_budget_remaining(1.0) == "100.0%"

    def test_none_value(self) -> None:
        assert format_budget_remaining(None) == "N/A"


class TestFormatProjectedExhaustion:
    """Tests for format_projected_exhaustion helper."""

    def test_days_and_hours(self) -> None:
        assert format_projected_exhaustion(259200.0) == "3d 0h"

    def test_hours_and_minutes(self) -> None:
        assert format_projected_exhaustion(9000.0) == "2h 30m"

    def test_minutes_only(self) -> None:
        assert format_projected_exhaustion(2700.0) == "45m"

    def test_zero_value(self) -> None:
        assert format_projected_exhaustion(0.0) == "N/A"

    def test_negative_value(self) -> None:
        assert format_projected_exhaustion(-100.0) == "N/A"

    def test_none_value(self) -> None:
        assert format_projected_exhaustion(None) == "N/A"

    def test_one_day_partial(self) -> None:
        # 1 day + 4 hours = 100800 seconds
        assert format_projected_exhaustion(100800.0) == "1d 4h"


class TestConditionCssClass:
    """Tests for condition_css_class helper."""

    def test_healthy(self) -> None:
        assert condition_css_class("healthy") == "status-healthy"

    def test_warning(self) -> None:
        assert condition_css_class("warning") == "status-warning"

    def test_critical(self) -> None:
        assert condition_css_class("critical") == "status-critical"

    def test_unknown(self) -> None:
        assert condition_css_class("unknown") == "status-neutral"

    def test_empty(self) -> None:
        assert condition_css_class("") == "status-neutral"
