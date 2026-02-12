"""Tests for Beeper UI services."""

import pytest
import respx
from httpx import Response

from beeper_ui.services.health_service import (
    HealthService,
    HealthServiceError,
)
from beeper_ui.services.source_service import SourceService, SourceServiceError


class TestSourceService:
    """Tests for SourceService."""

    @respx.mock
    def test_get_sources_success(self) -> None:
        """Test successful source fetch."""
        mock_response = {
            "sources": [
                {
                    "name": "prometheus-main",
                    "type": "prometheus",
                    "endpoint": "http://prometheus:9090",
                    "status": "connected",
                    "last_check": "2026-02-10T12:00:00Z",
                    "error": None,
                },
                {
                    "name": "loki-prod",
                    "type": "loki",
                    "endpoint": "http://loki:3100",
                    "status": "connected",
                    "last_check": "2026-02-10T12:00:00Z",
                    "error": None,
                },
            ]
        }

        respx.get("http://localhost:8080/api/v1/sources").mock(
            return_value=Response(200, json=mock_response)
        )

        service = SourceService("http://localhost:8080")
        sources = service.get_sources()

        assert len(sources) == 2
        # Should be sorted alphabetically
        assert sources[0].name == "loki-prod"
        assert sources[1].name == "prometheus-main"
        assert sources[1].status == "connected"
        assert sources[1].error is None

    @respx.mock
    def test_get_sources_with_error(self) -> None:
        """Test source with error details."""
        mock_response = {
            "sources": [
                {
                    "name": "loki-prod",
                    "type": "loki",
                    "endpoint": "http://loki:3100",
                    "status": "error",
                    "last_check": "2026-02-10T12:00:00Z",
                    "error": {
                        "type": "connection_refused",
                        "message": "Connection refused: check endpoint URL",
                        "details": "dial tcp 10.0.0.5:3100: connect: connection refused",
                    },
                }
            ]
        }

        respx.get("http://localhost:8080/api/v1/sources").mock(
            return_value=Response(200, json=mock_response)
        )

        service = SourceService("http://localhost:8080")
        sources = service.get_sources()

        assert len(sources) == 1
        assert sources[0].status == "error"
        assert sources[0].error is not None
        assert sources[0].error.type == "connection_refused"
        assert "Connection refused" in sources[0].error.message

    @respx.mock
    def test_get_sources_empty(self) -> None:
        """Test empty sources response."""
        respx.get("http://localhost:8080/api/v1/sources").mock(
            return_value=Response(200, json={"sources": []})
        )

        service = SourceService("http://localhost:8080")
        sources = service.get_sources()

        assert sources == []

    @respx.mock
    def test_get_sources_timeout(self) -> None:
        """Test timeout handling."""
        import httpx

        respx.get("http://localhost:8080/api/v1/sources").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        service = SourceService("http://localhost:8080", timeout=1.0)

        with pytest.raises(SourceServiceError) as exc_info:
            service.get_sources()

        assert "Timeout" in str(exc_info.value)

    @respx.mock
    def test_get_sources_connection_error(self) -> None:
        """Test connection error handling."""
        import httpx

        respx.get("http://localhost:8080/api/v1/sources").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service = SourceService("http://localhost:8080")

        with pytest.raises(SourceServiceError) as exc_info:
            service.get_sources()

        assert "Failed to connect" in str(exc_info.value)

    @respx.mock
    def test_get_sources_http_error(self) -> None:
        """Test HTTP error handling."""
        respx.get("http://localhost:8080/api/v1/sources").mock(
            return_value=Response(500, json={"error": "Internal server error"})
        )

        service = SourceService("http://localhost:8080")

        with pytest.raises(SourceServiceError) as exc_info:
            service.get_sources()

        assert "500" in str(exc_info.value)


class TestHealthService:
    """Tests for HealthService."""

    @respx.mock
    def test_get_health_success(self) -> None:
        """Test successful health fetch."""
        mock_response = {
            "components": {
                "operator": {"status": "healthy", "message": "Running"},
                "qdrant": {"status": "healthy", "message": "Connected"},
                "ingestion": {"status": "healthy", "message": "Buffer: 150/10000"},
            },
            "overall": "healthy",
        }

        respx.get("http://localhost:8080/api/v1/health/components").mock(
            return_value=Response(200, json=mock_response)
        )

        service = HealthService("http://localhost:8080")
        health = service.get_health()

        assert health.overall == "healthy"
        assert len(health.components) == 3
        assert health.components["operator"].status == "healthy"
        assert health.components["qdrant"].message == "Connected"

    @respx.mock
    def test_get_health_unhealthy(self) -> None:
        """Test unhealthy component."""
        mock_response = {
            "components": {
                "operator": {"status": "healthy", "message": "Running"},
                "qdrant": {"status": "unhealthy", "message": "Connection refused"},
            },
            "overall": "unhealthy",
        }

        respx.get("http://localhost:8080/api/v1/health/components").mock(
            return_value=Response(200, json=mock_response)
        )

        service = HealthService("http://localhost:8080")
        health = service.get_health()

        assert health.overall == "unhealthy"
        assert health.components["qdrant"].status == "unhealthy"

    @respx.mock
    def test_get_health_timeout(self) -> None:
        """Test timeout handling."""
        import httpx

        respx.get("http://localhost:8080/api/v1/health/components").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        service = HealthService("http://localhost:8080")

        with pytest.raises(HealthServiceError) as exc_info:
            service.get_health()

        assert "Timeout" in str(exc_info.value)

    @respx.mock
    def test_get_ingestion_stats_success(self) -> None:
        """Test successful ingestion stats fetch."""
        mock_response = {
            "buffer_size": 10000,
            "buffered_count": 150,
            "dropped_count": 0,
            "is_full": False,
        }

        respx.get("http://localhost:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=mock_response)
        )

        service = HealthService("http://localhost:8080")
        stats = service.get_ingestion_stats()

        assert stats.buffer_size == 10000
        assert stats.buffered_count == 150
        assert stats.dropped_count == 0
        assert stats.is_full is False

    @respx.mock
    def test_get_ingestion_stats_buffer_full(self) -> None:
        """Test ingestion stats when buffer is full."""
        mock_response = {
            "buffer_size": 10000,
            "buffered_count": 10000,
            "dropped_count": 500,
            "is_full": True,
        }

        respx.get("http://localhost:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=mock_response)
        )

        service = HealthService("http://localhost:8080")
        stats = service.get_ingestion_stats()

        assert stats.is_full is True
        assert stats.dropped_count == 500

    @respx.mock
    def test_is_operator_healthy_true(self) -> None:
        """Test operator health check returns true."""
        respx.get("http://localhost:8080/healthz").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        service = HealthService("http://localhost:8080")
        assert service.is_operator_healthy() is True

    @respx.mock
    def test_is_operator_healthy_false(self) -> None:
        """Test operator health check returns false on error."""
        respx.get("http://localhost:8080/healthz").mock(
            return_value=Response(503, json={"status": "unhealthy"})
        )

        service = HealthService("http://localhost:8080")
        assert service.is_operator_healthy() is False

    @respx.mock
    def test_is_operator_healthy_connection_error(self) -> None:
        """Test operator health check returns false on connection error."""
        import httpx

        respx.get("http://localhost:8080/healthz").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service = HealthService("http://localhost:8080")
        assert service.is_operator_healthy() is False
