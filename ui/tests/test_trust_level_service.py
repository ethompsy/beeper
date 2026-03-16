"""Tests for TrustLevelService — per-service autonomy trust levels (TL1-5)."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.trust_level_service import (
    DEFAULT_TRUST_LEVEL,
    MAX_TRUST_LEVEL,
    MIN_TRUST_LEVEL,
    SERVICE_TRUST_COLLECTION,
    TRUST_LEVEL_DEFINITIONS,
    TrustLevelConfig,
    TrustLevelService,
    TrustLevelServiceError,
)

# ---------- Fixtures & Helpers ----------


def _make_autonomy_payload(
    service_name: str = "payment-api",
    autonomy_level: int = 3,
    autonomy_updated_by: str = "admin@test.com",
    autonomy_updated_at: str = "2026-03-15T10:00:00+00:00",
    autonomy_reason: str | None = "Proven reliable",
    autonomy_previous_level: int | None = 2,
    # Include KB trust fields to ensure they're preserved
    trust_level: str = "trusted",
    accuracy_pct: float = 95.0,
) -> dict:
    """Create a mock Qdrant payload with autonomy trust fields."""
    return {
        "service_name": service_name,
        # KB trust fields (should be preserved, not touched)
        "trust_level": trust_level,
        "accuracy_pct": accuracy_pct,
        # Autonomy trust fields
        "autonomy_level": autonomy_level,
        "autonomy_updated_by": autonomy_updated_by,
        "autonomy_updated_at": autonomy_updated_at,
        "autonomy_reason": autonomy_reason,
        "autonomy_previous_level": autonomy_previous_level,
    }


def _make_point(
    point_id: str = "test-uuid-1",
    payload: dict | None = None,
) -> MagicMock:
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = payload if payload is not None else _make_autonomy_payload()
    return point


def _make_service(mock_client: MagicMock | None = None) -> TrustLevelService:
    """Create a TrustLevelService with mocked Qdrant client."""
    service = TrustLevelService(host="localhost", port=6333)
    if mock_client is not None:
        service._client = mock_client
    return service


# ---------- TrustLevelConfig Tests ----------


class TestTrustLevelConfig:
    """Tests for TrustLevelConfig dataclass."""

    def test_from_qdrant_full_payload(self) -> None:
        payload = _make_autonomy_payload()
        config = TrustLevelConfig.from_qdrant(payload)
        assert config.service_name == "payment-api"
        assert config.trust_level == 3
        assert config.updated_by == "admin@test.com"
        assert config.updated_at == "2026-03-15T10:00:00+00:00"
        assert config.reason == "Proven reliable"
        assert config.previous_level == 2

    def test_from_qdrant_minimal_payload(self) -> None:
        payload = {"service_name": "auth-service", "autonomy_level": 1}
        config = TrustLevelConfig.from_qdrant(payload)
        assert config.service_name == "auth-service"
        assert config.trust_level == 1
        assert config.updated_by == ""
        assert config.updated_at == ""
        assert config.reason is None
        assert config.previous_level is None

    def test_from_qdrant_missing_autonomy_level_defaults(self) -> None:
        payload = {"service_name": "test-svc"}
        config = TrustLevelConfig.from_qdrant(payload)
        assert config.trust_level == DEFAULT_TRUST_LEVEL

    def test_from_qdrant_empty_payload(self) -> None:
        config = TrustLevelConfig.from_qdrant({})
        assert config.service_name == ""
        assert config.trust_level == DEFAULT_TRUST_LEVEL


# ---------- TrustLevelService.get_service_trust_level Tests ----------


class TestGetServiceTrustLevel:
    """Tests for get_service_trust_level method."""

    def test_returns_config_when_found(self) -> None:
        mock_client = MagicMock()
        point = _make_point()
        mock_client.scroll.return_value = ([point], None)

        service = _make_service(mock_client)
        result = service.get_service_trust_level("payment-api")

        assert result is not None
        assert result.service_name == "payment-api"
        assert result.trust_level == 3
        mock_client.scroll.assert_called_once()

    def test_returns_none_when_not_found(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.get_service_trust_level("nonexistent")

        assert result is None

    def test_returns_none_when_no_autonomy_level(self) -> None:
        """Service has KB trust but no autonomy level configured."""
        mock_client = MagicMock()
        payload = {"service_name": "test-svc", "trust_level": "draft"}
        point = _make_point(payload=payload)
        mock_client.scroll.return_value = ([point], None)

        service = _make_service(mock_client)
        result = service.get_service_trust_level("test-svc")

        assert result is None

    def test_raises_on_qdrant_error(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.side_effect = RuntimeError("Qdrant unavailable")

        service = _make_service(mock_client)
        with pytest.raises(TrustLevelServiceError, match="Failed to get trust level"):
            service.get_service_trust_level("payment-api")


# ---------- TrustLevelService.get_all_trust_levels Tests ----------


class TestGetAllTrustLevels:
    """Tests for get_all_trust_levels method."""

    def test_returns_all_configured_levels(self) -> None:
        mock_client = MagicMock()
        points = [
            _make_point("id1", _make_autonomy_payload("svc-a", 2)),
            _make_point("id2", _make_autonomy_payload("svc-b", 4)),
        ]
        mock_client.scroll.return_value = (points, None)

        service = _make_service(mock_client)
        result = service.get_all_trust_levels()

        assert len(result) == 2
        assert result[0].service_name == "svc-a"
        assert result[0].trust_level == 2
        assert result[1].service_name == "svc-b"
        assert result[1].trust_level == 4

    def test_filters_out_entries_without_autonomy(self) -> None:
        mock_client = MagicMock()
        points = [
            _make_point("id1", _make_autonomy_payload("svc-a", 3)),
            _make_point("id2", {"service_name": "svc-b", "trust_level": "draft"}),
        ]
        mock_client.scroll.return_value = (points, None)

        service = _make_service(mock_client)
        result = service.get_all_trust_levels()

        assert len(result) == 1
        assert result[0].service_name == "svc-a"

    def test_returns_empty_list_when_no_entries(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.get_all_trust_levels()

        assert result == []

    def test_raises_on_qdrant_error(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.side_effect = RuntimeError("Qdrant unavailable")

        service = _make_service(mock_client)
        with pytest.raises(TrustLevelServiceError, match="Failed to list"):
            service.get_all_trust_levels()


# ---------- TrustLevelService.set_trust_level Tests ----------


class TestSetTrustLevel:
    """Tests for set_trust_level method."""

    def test_creates_new_entry(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.set_trust_level("new-svc", 3, "admin@test.com", "Initial config")

        assert result.service_name == "new-svc"
        assert result.trust_level == 3
        assert result.updated_by == "admin@test.com"
        assert result.reason == "Initial config"
        assert result.previous_level is None
        mock_client.upsert.assert_called_once()

    def test_updates_existing_entry(self) -> None:
        mock_client = MagicMock()
        existing_payload = _make_autonomy_payload("payment-api", 2)
        point = _make_point("existing-id", existing_payload)
        mock_client.scroll.return_value = ([point], None)

        service = _make_service(mock_client)
        result = service.set_trust_level("payment-api", 4, "admin@test.com")

        assert result.trust_level == 4
        assert result.previous_level == 2
        # Verify upsert used the existing point ID
        call_args = mock_client.upsert.call_args
        upserted_point = call_args.kwargs["points"][0]
        assert upserted_point.id == "existing-id"

    def test_preserves_kb_trust_fields(self) -> None:
        mock_client = MagicMock()
        existing_payload = {
            "service_name": "payment-api",
            "trust_level": "trusted",
            "accuracy_pct": 92.5,
            "total_entries": 20,
            "autonomy_level": 1,
        }
        point = _make_point("existing-id", existing_payload)
        mock_client.scroll.return_value = ([point], None)

        service = _make_service(mock_client)
        service.set_trust_level("payment-api", 3, "admin@test.com")

        call_args = mock_client.upsert.call_args
        upserted_payload = call_args.kwargs["points"][0].payload
        # KB fields preserved
        assert upserted_payload["trust_level"] == "trusted"
        assert upserted_payload["accuracy_pct"] == 92.5
        assert upserted_payload["total_entries"] == 20
        # Autonomy fields updated
        assert upserted_payload["autonomy_level"] == 3

    def test_rejects_level_below_minimum(self) -> None:
        service = _make_service(MagicMock())
        with pytest.raises(ValueError, match="Trust level must be"):
            service.set_trust_level("svc", 0, "admin")

    def test_rejects_level_above_maximum(self) -> None:
        service = _make_service(MagicMock())
        with pytest.raises(ValueError, match="Trust level must be"):
            service.set_trust_level("svc", 6, "admin")

    def test_rejects_non_integer_level(self) -> None:
        service = _make_service(MagicMock())
        with pytest.raises(ValueError, match="Trust level must be"):
            service.set_trust_level("svc", "high", "admin")  # type: ignore[arg-type]

    def test_rejects_negative_level(self) -> None:
        service = _make_service(MagicMock())
        with pytest.raises(ValueError, match="Trust level must be"):
            service.set_trust_level("svc", -1, "admin")

    def test_raises_on_qdrant_error(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.side_effect = RuntimeError("Qdrant unavailable")

        service = _make_service(mock_client)
        with pytest.raises(TrustLevelServiceError, match="Failed to set"):
            service.set_trust_level("svc", 3, "admin")

    def test_level_boundary_1(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.set_trust_level("svc", 1, "admin")
        assert result.trust_level == 1

    def test_level_boundary_5(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.set_trust_level("svc", 5, "admin")
        assert result.trust_level == 5


# ---------- TrustLevelService.get_effective_trust_level Tests ----------


class TestGetEffectiveTrustLevel:
    """Tests for get_effective_trust_level method."""

    def test_returns_configured_level(self) -> None:
        mock_client = MagicMock()
        point = _make_point(payload=_make_autonomy_payload("svc", 4))
        mock_client.scroll.return_value = ([point], None)

        service = _make_service(mock_client)
        result = service.get_effective_trust_level("svc")
        assert result == 4

    def test_returns_default_when_not_configured(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        service = _make_service(mock_client)
        result = service.get_effective_trust_level("unconfigured-svc")
        assert result == DEFAULT_TRUST_LEVEL

    def test_returns_default_on_qdrant_error(self) -> None:
        mock_client = MagicMock()
        mock_client.scroll.side_effect = RuntimeError("Qdrant unavailable")

        service = _make_service(mock_client)
        result = service.get_effective_trust_level("svc")
        assert result == DEFAULT_TRUST_LEVEL


# ---------- TrustLevelService lifecycle Tests ----------


class TestServiceLifecycle:
    """Tests for service initialization and cleanup."""

    def test_close_cleans_up_client(self) -> None:
        mock_client = MagicMock()
        service = _make_service(mock_client)
        service.close()
        mock_client.close.assert_called_once()
        assert service._client is None

    def test_close_when_no_client(self) -> None:
        service = TrustLevelService(host="localhost")
        service.close()  # Should not raise

    def test_client_property_creates_client(self) -> None:
        with patch(
            "beeper_ui.services.trust_level_service.QdrantClient"
        ) as mock_qdrant:
            service = TrustLevelService(host="localhost", port=6333)
            _ = service.client
            mock_qdrant.assert_called_once_with(host="localhost", port=6333)


# ---------- Constants Tests ----------


class TestConstants:
    """Tests for module-level constants."""

    def test_trust_level_definitions_complete(self) -> None:
        for level in range(MIN_TRUST_LEVEL, MAX_TRUST_LEVEL + 1):
            assert level in TRUST_LEVEL_DEFINITIONS
            assert "name" in TRUST_LEVEL_DEFINITIONS[level]
            assert "description" in TRUST_LEVEL_DEFINITIONS[level]

    def test_default_trust_level_is_one(self) -> None:
        assert DEFAULT_TRUST_LEVEL == 1

    def test_collection_name_matches_kb_service(self) -> None:
        assert SERVICE_TRUST_COLLECTION == "service_trust_levels"
