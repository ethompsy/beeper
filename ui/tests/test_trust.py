"""Tests for Graduated Authoring Trust (Story 5-4)."""

from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from beeper_ui.services.kb_service import (
    Correction,
    KBEntry,
    KBService,
    KBServiceError,
    ServiceTrustLevel,
)


def _make_trust_payload(
    service_name: str = "api-gateway",
    trust_level: str = "draft",
    accuracy_pct: float = 85.0,
    total_entries: int = 12,
    reviewed_entries: int = 2,
    correct_entries: int = 10,
    manually_adjusted: bool = False,
    manual_reason: str = "",
) -> dict:
    """Create a mock service trust level payload."""
    return {
        "service_name": service_name,
        "trust_level": trust_level,
        "accuracy_pct": accuracy_pct,
        "total_entries": total_entries,
        "reviewed_entries": reviewed_entries,
        "correct_entries": correct_entries,
        "last_updated": "2026-03-07T12:00:00+00:00",
        "manually_adjusted": manually_adjusted,
        "manual_reason": manual_reason,
    }


def _make_entry(
    entry_id: str = "kb-test123",
    service: str = "api-gateway",
    author: str = "beeper",
    auto_published: bool = False,
) -> KBEntry:
    """Create a mock KBEntry for testing."""
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type="investigation",
        title="Test Entry",
        content="Test content",
        service=service,
        created_at=None,
        updated_at=None,
        author=author,
        version=1,
        tags=[],
        auto_published=auto_published,
    )


def _make_correction_payload(
    correction_id: str = "corr-abc123",
    entry_id: str = "kb-test123",
    status: str = "pending",
) -> dict:
    """Create a mock correction payload."""
    return {
        "correction_id": correction_id,
        "entry_id": entry_id,
        "messages": [
            {
                "role": "user",
                "content": "Fix this",
                "timestamp": "2026-03-07T10:00:00+00:00",
            },
            {
                "role": "assistant",
                "content": "OK",
                "timestamp": "2026-03-07T10:01:00+00:00",
            },
        ],
        "status": status,
        "summary": "Fix",
        "created_at": "2026-03-07T10:00:00+00:00",
        "updated_at": "2026-03-07T10:01:00+00:00",
    }


# ── ServiceTrustLevel Data Model Tests ──


class TestServiceTrustLevel:
    """Tests for ServiceTrustLevel dataclass."""

    def test_from_qdrant(self) -> None:
        payload = _make_trust_payload()
        trust = ServiceTrustLevel.from_qdrant(payload)
        assert trust.service_name == "api-gateway"
        assert trust.trust_level == "draft"
        assert trust.accuracy_pct == 85.0
        assert trust.total_entries == 12
        assert trust.reviewed_entries == 2
        assert trust.correct_entries == 10
        assert trust.last_updated == "2026-03-07T12:00:00+00:00"
        assert trust.manually_adjusted is False
        assert trust.manual_reason == ""

    def test_from_qdrant_defaults(self) -> None:
        trust = ServiceTrustLevel.from_qdrant({})
        assert trust.service_name == ""
        assert trust.trust_level == "draft"
        assert trust.accuracy_pct == 0.0
        assert trust.total_entries == 0
        assert trust.reviewed_entries == 0
        assert trust.correct_entries == 0
        assert trust.last_updated == ""
        assert trust.manually_adjusted is False
        assert trust.manual_reason == ""

    def test_from_qdrant_trusted(self) -> None:
        payload = _make_trust_payload(
            trust_level="trusted",
            accuracy_pct=95.0,
            total_entries=20,
            correct_entries=19,
            reviewed_entries=1,
        )
        trust = ServiceTrustLevel.from_qdrant(payload)
        assert trust.trust_level == "trusted"
        assert trust.accuracy_pct == 95.0

    def test_from_qdrant_manual_override(self) -> None:
        payload = _make_trust_payload(
            manually_adjusted=True,
            manual_reason="Admin override for testing",
        )
        trust = ServiceTrustLevel.from_qdrant(payload)
        assert trust.manually_adjusted is True
        assert trust.manual_reason == "Admin override for testing"


class TestKBEntryAutoPublished:
    """Tests for auto_published field on KBEntry."""

    def test_auto_published_default_false(self) -> None:
        entry = _make_entry()
        assert entry.auto_published is False

    def test_auto_published_true(self) -> None:
        entry = _make_entry(auto_published=True)
        assert entry.auto_published is True

    def test_from_qdrant_auto_published(self) -> None:
        payload = {
            "entry_id": "kb-test",
            "entry_type": "investigation",
            "title": "Test",
            "content": "Content",
            "service": "api-gateway",
            "created_at": "2026-03-07T12:00:00+00:00",
            "updated_at": "2026-03-07T12:00:00+00:00",
            "author": "beeper",
            "version": 1,
            "tags": [],
            "auto_published": True,
        }
        entry = KBEntry.from_qdrant("point-1", payload)
        assert entry.auto_published is True

    def test_from_qdrant_auto_published_missing(self) -> None:
        payload = {
            "entry_id": "kb-test",
            "entry_type": "investigation",
            "title": "Test",
            "content": "Content",
            "service": "api-gateway",
            "created_at": "2026-03-07T12:00:00+00:00",
            "updated_at": "2026-03-07T12:00:00+00:00",
            "author": "beeper",
            "version": 1,
            "tags": [],
        }
        entry = KBEntry.from_qdrant("point-1", payload)
        assert entry.auto_published is False


# ── KBService Trust Level CRUD Tests ──


class TestKBServiceTrustCRUD:
    """Tests for KBService trust level methods."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_service_trust(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_trust_payload()
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        trust = svc.get_service_trust("api-gateway")
        assert trust is not None
        assert trust.service_name == "api-gateway"
        assert trust.trust_level == "draft"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_service_trust_not_found(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        trust = svc.get_service_trust("unknown-service")
        assert trust is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_service_trust_qdrant_error(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Connection refused")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to get service trust"):
            svc.get_service_trust("api-gateway")

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_upsert_service_trust_new(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        # get_service_trust returns None (no existing record)
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        trust = svc.upsert_service_trust(
            service_name="api-gateway",
            trust_level="draft",
            accuracy_pct=85.0,
            total_entries=12,
            reviewed_entries=2,
            correct_entries=10,
        )
        assert trust.service_name == "api-gateway"
        assert trust.trust_level == "draft"
        assert trust.accuracy_pct == 85.0
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_upsert_service_trust_existing(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_trust_payload()
        mock_point.id = "existing-point-id"
        # First scroll for get_service_trust, second for reuse point_id
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        trust = svc.upsert_service_trust(
            service_name="api-gateway",
            trust_level="trusted",
            accuracy_pct=95.0,
            total_entries=20,
            reviewed_entries=1,
            correct_entries=19,
        )
        assert trust.trust_level == "trusted"
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_upsert_service_trust_invalid_level(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        trust = svc.upsert_service_trust(
            service_name="api-gateway",
            trust_level="invalid",
            accuracy_pct=50.0,
            total_entries=5,
            reviewed_entries=0,
            correct_entries=5,
        )
        assert trust.trust_level == "draft"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_all_service_trusts(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        p1 = MagicMock()
        p1.payload = _make_trust_payload(service_name="api-gateway")
        p2 = MagicMock()
        p2.payload = _make_trust_payload(
            service_name="auth-service", trust_level="trusted"
        )
        mock_client.scroll.return_value = ([p1, p2], None)

        svc = KBService()
        trusts = svc.get_all_service_trusts()
        assert len(trusts) == 2
        assert trusts[0].service_name == "api-gateway"
        assert trusts[1].service_name == "auth-service"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_all_service_trusts_empty(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        trusts = svc.get_all_service_trusts()
        assert trusts == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_all_service_trusts_error(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Timeout")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to get service trusts"):
            svc.get_all_service_trusts()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_set_manual_trust_override(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_trust_payload()
        mock_point.id = "existing-id"
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        trust = svc.set_manual_trust_override(
            service_name="api-gateway",
            trust_level="trusted",
            reason="Admin approved",
        )
        assert trust.trust_level == "trusted"
        assert trust.manually_adjusted is True
        assert trust.manual_reason == "Admin approved"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_set_manual_trust_override_no_existing(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        trust = svc.set_manual_trust_override(
            service_name="new-service",
            trust_level="trusted",
            reason="Fast-track",
        )
        assert trust.trust_level == "trusted"
        assert trust.total_entries == 0
        assert trust.accuracy_pct == 0.0


# ── Accuracy Calculation Tests ──


class TestAccuracyCalculation:
    """Tests for calculate_service_accuracy."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_accuracy_all_correct(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 10 entries, no learning patterns
        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}
        mock_client.scroll.side_effect = [
            (entries, None),  # calculate: entries
            ([], None),       # calculate: learning patterns
        ]

        svc = KBService()
        metrics = svc.calculate_service_accuracy("api-gateway")
        assert metrics["total_entries"] == 10
        assert metrics["reviewed_entries"] == 0
        assert metrics["correct_entries"] == 10
        assert metrics["accuracy_pct"] == 100.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_accuracy_some_corrected(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # First scroll: knowledge entries
        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        # Second scroll: learning patterns (2 entries corrected)
        patterns = [MagicMock(), MagicMock()]
        patterns[0].payload = {
            "pattern_id": "lrn-1",
            "entry_id": "kb-0",
            "correction_id": "corr-1",
            "service_name": "api-gateway",
            "category": "missing_context",
            "description": "Test",
            "original_snippet": "",
            "corrected_snippet": "",
            "created_at": "2026-03-07T12:00:00+00:00",
        }
        patterns[1].payload = {
            "pattern_id": "lrn-2",
            "entry_id": "kb-1",
            "correction_id": "corr-2",
            "service_name": "api-gateway",
            "category": "wrong_conclusion",
            "description": "Test",
            "original_snippet": "",
            "corrected_snippet": "",
            "created_at": "2026-03-07T12:00:00+00:00",
        }

        # First call for entries, second for learning patterns
        mock_client.scroll.side_effect = [
            (entries, None),
            (patterns, None),
        ]

        svc = KBService()
        metrics = svc.calculate_service_accuracy("api-gateway")
        assert metrics["total_entries"] == 10
        assert metrics["reviewed_entries"] == 2
        assert metrics["correct_entries"] == 8
        assert metrics["accuracy_pct"] == 80.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_accuracy_no_entries(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        metrics = svc.calculate_service_accuracy("empty-service")
        assert metrics["total_entries"] == 0
        assert metrics["accuracy_pct"] == 0.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_accuracy_qdrant_error(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Timeout")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to calculate accuracy"):
            svc.calculate_service_accuracy("api-gateway")


# ── Trust Graduation Tests ──


class TestTrustGraduation:
    """Tests for evaluate_trust_graduation."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_graduation_to_trusted(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 15 entries, 0 corrected → 100% accuracy
        entries = [MagicMock() for _ in range(15)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        # scroll calls: calculate_accuracy(entries), calculate_accuracy(patterns),
        # get_service_trust, upsert(get_service_trust, get_point_id)
        mock_client.scroll.side_effect = [
            (entries, None),   # calculate_service_accuracy: entries
            ([], None),        # calculate_service_accuracy: patterns
            ([], None),        # get_service_trust: not found
            ([], None),        # upsert_service_trust: get_service_trust
            ([], None),        # upsert_service_trust: find existing
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "trusted"
        assert trust.accuracy_pct == 100.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_no_graduation_insufficient_entries(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 5 entries (below 10 threshold)
        entries = [MagicMock() for _ in range(5)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        mock_client.scroll.side_effect = [
            (entries, None),   # calculate: entries
            ([], None),        # calculate: patterns
            ([], None),        # get_service_trust
            ([], None),        # upsert: get_service_trust
            ([], None),        # upsert: find existing
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "draft"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_downgrade_to_draft(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 10 entries, 3 corrected → 70% accuracy (below 80% threshold)
        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        patterns = []
        for i in range(3):
            p = MagicMock()
            p.payload = {
                "pattern_id": f"lrn-{i}",
                "entry_id": f"kb-{i}",
                "correction_id": f"corr-{i}",
                "service_name": "api-gateway",
                "category": "missing_context",
                "description": "test",
                "original_snippet": "",
                "corrected_snippet": "",
                "created_at": "2026-03-07T12:00:00+00:00",
            }
            patterns.append(p)

        # Existing trust is "trusted"
        trusted_point = MagicMock()
        trusted_point.payload = _make_trust_payload(
            trust_level="trusted", accuracy_pct=95.0
        )
        trusted_point.id = "existing-id"

        mock_client.scroll.side_effect = [
            (entries, None),           # calculate: entries
            (patterns, None),          # calculate: patterns
            ([trusted_point], None),   # get_service_trust
            ([trusted_point], None),   # upsert: get_service_trust
            ([trusted_point], None),   # upsert: find existing
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "draft"
        assert trust.accuracy_pct == 70.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_no_change_no_entries(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        result = svc.evaluate_trust_graduation("empty-service")
        assert result is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_manual_override_not_changed(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 15 entries, all correct → would normally graduate
        entries = [MagicMock() for _ in range(15)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        # Existing trust is manually set to "draft"
        manual_point = MagicMock()
        manual_point.payload = _make_trust_payload(
            trust_level="draft",
            manually_adjusted=True,
            manual_reason="Keep in draft for testing",
        )

        mock_client.scroll.side_effect = [
            (entries, None),           # calculate: entries
            ([], None),                # calculate: patterns
            ([manual_point], None),    # get_service_trust
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "draft"
        assert trust.manually_adjusted is True


# ── Auto-Publish Tests ──


class TestAutoPublish:
    """Tests for should_auto_publish and create_entry integration."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_should_auto_publish_trusted(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_trust_payload(trust_level="trusted")
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        assert svc.should_auto_publish("api-gateway") is True

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_should_auto_publish_draft(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_trust_payload(trust_level="draft")
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        assert svc.should_auto_publish("api-gateway") is False

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_should_auto_publish_no_record(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        assert svc.should_auto_publish("new-service") is False

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_should_auto_publish_qdrant_error(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Qdrant down")

        svc = KBService()
        # Returns False on error (non-blocking)
        assert svc.should_auto_publish("api-gateway") is False

    @patch("beeper_ui.services.kb_service.EmbeddingService")
    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_auto_published_trusted(
        self, mock_client_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed
        mock_embed.get_embedding.return_value = [0.1] * 1536

        # should_auto_publish → get_service_trust → trusted
        trust_point = MagicMock()
        trust_point.payload = _make_trust_payload(trust_level="trusted")
        mock_client.scroll.return_value = ([trust_point], None)

        svc = KBService()
        entry_id = svc.create_entry(
            title="Test",
            content="Content",
            entry_type="investigation",
            service="api-gateway",
            author="beeper",
        )
        assert entry_id.startswith("kb-")

        # Check that auto_published=True in the first upsert (entry creation)
        # create_entry calls upsert twice: once for entry, once for version
        first_upsert = mock_client.upsert.call_args_list[0]
        points = first_upsert.kwargs.get("points") or first_upsert[1].get("points")
        payload = points[0].payload
        assert payload["auto_published"] is True

    @patch("beeper_ui.services.kb_service.EmbeddingService")
    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_not_auto_published_draft(
        self, mock_client_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed
        mock_embed.get_embedding.return_value = [0.1] * 1536

        # should_auto_publish → get_service_trust → draft
        draft_point = MagicMock()
        draft_point.payload = _make_trust_payload(trust_level="draft")
        mock_client.scroll.return_value = ([draft_point], None)

        svc = KBService()
        svc.create_entry(
            title="Test",
            content="Content",
            entry_type="investigation",
            service="api-gateway",
            author="beeper",
        )

        first_upsert = mock_client.upsert.call_args_list[0]
        points = first_upsert.kwargs.get("points") or first_upsert[1].get("points")
        payload = points[0].payload
        assert payload["auto_published"] is False

    @patch("beeper_ui.services.kb_service.EmbeddingService")
    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_not_auto_published_human_author(
        self, mock_client_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed
        mock_embed.get_embedding.return_value = [0.1] * 1536

        # Even though service is trusted, human author → no auto-publish
        trust_point = MagicMock()
        trust_point.payload = _make_trust_payload(trust_level="trusted")
        mock_client.scroll.return_value = ([trust_point], None)

        svc = KBService()
        svc.create_entry(
            title="Test",
            content="Content",
            entry_type="runbook",
            service="api-gateway",
            author="engineer",
        )

        first_upsert = mock_client.upsert.call_args_list[0]
        points = first_upsert.kwargs.get("points") or first_upsert[1].get("points")
        payload = points[0].payload
        assert payload["auto_published"] is False


# ── Trust Settings Route Tests ──


class TestTrustSettingsRoutes:
    """Tests for trust settings page and override routes."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_settings_page(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_all_service_trusts.return_value = [
            ServiceTrustLevel.from_qdrant(
                _make_trust_payload(
                    service_name="api-gateway",
                    trust_level="trusted",
                    accuracy_pct=95.0,
                )
            ),
            ServiceTrustLevel.from_qdrant(
                _make_trust_payload(
                    service_name="auth-service",
                    trust_level="draft",
                    accuracy_pct=75.0,
                )
            ),
        ]

        response = client.get("/knowledge/trust-settings")
        assert response.status_code == 200
        assert b"Trust Settings" in response.data
        assert b"api-gateway" in response.data
        assert b"auth-service" in response.data
        assert b"trusted" in response.data
        assert b"95.0%" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_settings_page_empty(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_all_service_trusts.return_value = []

        response = client.get("/knowledge/trust-settings")
        assert response.status_code == 200
        assert b"No trust records yet" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_settings_page_error(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_all_service_trusts.side_effect = KBServiceError(
            "Qdrant down"
        )

        response = client.get("/knowledge/trust-settings")
        assert response.status_code == 200
        assert b"Unable to load trust data" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_success(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.set_manual_trust_override.return_value = (
            ServiceTrustLevel.from_qdrant(
                _make_trust_payload(
                    trust_level="trusted",
                    manually_adjusted=True,
                    manual_reason="Admin approved",
                )
            )
        )

        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "trusted", "reason": "Admin approved"},
        )
        assert response.status_code == 200
        assert b"Override applied" in response.data
        mock_svc.set_manual_trust_override.assert_called_once_with(
            service_name="api-gateway",
            trust_level="trusted",
            reason="Admin approved",
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_invalid_level(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "superadmin", "reason": "test"},
        )
        assert response.status_code == 400
        assert b"Invalid trust level" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_missing_reason(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "trusted", "reason": ""},
        )
        assert response.status_code == 400
        assert b"Reason is required" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_reason_truncated(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.set_manual_trust_override.return_value = (
            ServiceTrustLevel.from_qdrant(
                _make_trust_payload(
                    trust_level="draft",
                    manually_adjusted=True,
                    manual_reason="x" * 500,
                )
            )
        )

        long_reason = "x" * 600
        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "draft", "reason": long_reason},
        )
        assert response.status_code == 200
        # Reason should be truncated to 500 chars
        call_args = mock_svc.set_manual_trust_override.call_args
        assert len(call_args.kwargs["reason"]) == 500

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_service_error(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.set_manual_trust_override.side_effect = KBServiceError(
            "Qdrant error"
        )

        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "trusted", "reason": "test reason"},
        )
        assert response.status_code == 500


# ── Entry Auto-Published Badge Route Test ──

# TestEntryAutoPublishedBadge was removed under Task 6.3 — both tests called
# `client.get("/knowledge/<id>")` (bare) to check for the "Auto-published"
# badge on the entry detail page. That page is retired and now
# 302-redirects to the React app, so the badge lived on a page that no
# longer renders here; there is no remaining Python-level surface to assert
# against.


# ── Trust Re-evaluation Hook Tests ──


class TestTrustReEvaluationHook:
    """Tests for trust re-evaluation in apply revision route."""

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_apply_triggers_trust_evaluation(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.return_value = [
            {
                "category": "missing_context",
                "description": "Test",
                "original_snippet": "a",
                "corrected_snippet": "b",
            },
        ]

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        assert response.status_code == 200
        mock_svc.evaluate_trust_graduation.assert_called_once_with(
            "api-gateway"
        )

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_evaluation_failure_nonblocking(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.return_value = []

        # Trust evaluation fails
        mock_svc.evaluate_trust_graduation.side_effect = KBServiceError(
            "Qdrant error"
        )

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        # Apply still succeeds even though trust evaluation failed
        assert response.status_code == 200

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_evaluation_no_service_uses_general(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry(service=None)
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.return_value = []

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        assert response.status_code == 200
        mock_svc.evaluate_trust_graduation.assert_called_once_with(
            "general"
        )


# ── Boundary Tests for Trust Graduation ──


class TestTrustGraduationBoundaries:
    """Boundary tests for trust graduation thresholds."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_graduation_exactly_10_entries_90_pct(
        self, mock_client_class: MagicMock
    ) -> None:
        """Exactly 10 entries, 1 corrected = 90% → should graduate."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        pattern = MagicMock()
        pattern.payload = {
            "pattern_id": "lrn-1",
            "entry_id": "kb-0",
            "correction_id": "corr-1",
            "service_name": "api-gateway",
            "category": "missing_context",
            "description": "test",
            "original_snippet": "",
            "corrected_snippet": "",
            "created_at": "2026-03-07T12:00:00+00:00",
        }

        mock_client.scroll.side_effect = [
            (entries, None),       # calculate: entries
            ([pattern], None),     # calculate: patterns
            ([], None),            # get_service_trust
            ([], None),            # upsert: find existing
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "trusted"
        assert trust.accuracy_pct == 90.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_no_graduation_9_entries_100_pct(
        self, mock_client_class: MagicMock
    ) -> None:
        """9 entries, all correct → 100% but below 10 threshold."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        entries = [MagicMock() for _ in range(9)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        mock_client.scroll.side_effect = [
            (entries, None),
            ([], None),
            ([], None),
            ([], None),
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "draft"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_no_graduation_10_entries_89_pct(
        self, mock_client_class: MagicMock
    ) -> None:
        """10 entries, 2 corrected = 80% → below 90% threshold."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        patterns = []
        for i in range(2):
            p = MagicMock()
            p.payload = {
                "pattern_id": f"lrn-{i}",
                "entry_id": f"kb-{i}",
                "correction_id": f"corr-{i}",
                "service_name": "api-gateway",
                "category": "missing_context",
                "description": "test",
                "original_snippet": "",
                "corrected_snippet": "",
                "created_at": "2026-03-07T12:00:00+00:00",
            }
            patterns.append(p)

        mock_client.scroll.side_effect = [
            (entries, None),
            (patterns, None),
            ([], None),
            ([], None),
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "draft"
        assert trust.accuracy_pct == 80.0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_no_downgrade_at_exactly_80_pct(
        self, mock_client_class: MagicMock
    ) -> None:
        """Trusted service at exactly 80% → should NOT downgrade."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        entries = [MagicMock() for _ in range(10)]
        for i, e in enumerate(entries):
            e.payload = {"entry_id": f"kb-{i}"}

        patterns = []
        for i in range(2):
            p = MagicMock()
            p.payload = {
                "pattern_id": f"lrn-{i}",
                "entry_id": f"kb-{i}",
                "correction_id": f"corr-{i}",
                "service_name": "api-gateway",
                "category": "missing_context",
                "description": "test",
                "original_snippet": "",
                "corrected_snippet": "",
                "created_at": "2026-03-07T12:00:00+00:00",
            }
            patterns.append(p)

        trusted_point = MagicMock()
        trusted_point.payload = _make_trust_payload(
            trust_level="trusted", accuracy_pct=95.0
        )
        trusted_point.id = "existing-id"

        mock_client.scroll.side_effect = [
            (entries, None),
            (patterns, None),
            ([trusted_point], None),
            ([trusted_point], None),
        ]

        svc = KBService()
        trust = svc.evaluate_trust_graduation("api-gateway")
        assert trust is not None
        assert trust.trust_level == "trusted"
        assert trust.accuracy_pct == 80.0


# ── Additional Auto-Publish Edge Case Tests ──


class TestAutoPublishEdgeCases:
    """Additional edge case tests for auto-publish."""

    @patch("beeper_ui.services.kb_service.EmbeddingService")
    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_no_service_no_auto_publish(
        self, mock_client_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """service=None should not check trust or set auto_published."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed
        mock_embed.get_embedding.return_value = [0.1] * 1536

        # scroll should NOT be called for trust check
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        svc.create_entry(
            title="Test",
            content="Content",
            entry_type="investigation",
            service=None,
            author="beeper",
        )

        first_upsert = mock_client.upsert.call_args_list[0]
        points = (
            first_upsert.kwargs.get("points")
            or first_upsert[1].get("points")
        )
        payload = points[0].payload
        assert payload["auto_published"] is False

    @patch("beeper_ui.services.kb_service.EmbeddingService")
    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_investigation_author_trusted(
        self, mock_client_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """author='investigation' with trusted service → auto_published."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed
        mock_embed.get_embedding.return_value = [0.1] * 1536

        trust_point = MagicMock()
        trust_point.payload = _make_trust_payload(trust_level="trusted")
        mock_client.scroll.return_value = ([trust_point], None)

        svc = KBService()
        svc.create_entry(
            title="Test",
            content="Content",
            entry_type="investigation",
            service="api-gateway",
            author="investigation",
        )

        first_upsert = mock_client.upsert.call_args_list[0]
        points = (
            first_upsert.kwargs.get("points")
            or first_upsert[1].get("points")
        )
        payload = points[0].payload
        assert payload["auto_published"] is True


# ── Additional Route Validation Tests ──


class TestTrustRouteValidation:
    """Tests for trust route input validation."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_invalid_service_name(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        response = client.post(
            "/knowledge/trust-settings/invalid service!/override",
            data={"trust_level": "trusted", "reason": "test"},
        )
        assert response.status_code == 400
        assert b"Invalid service name" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_service_name_too_long(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        long_name = "a" * 101
        response = client.post(
            f"/knowledge/trust-settings/{long_name}/override",
            data={"trust_level": "trusted", "reason": "test"},
        )
        assert response.status_code == 400
        assert b"Invalid service name" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_trust_override_service_error_body(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        """Verify error response does not leak internal details."""
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.set_manual_trust_override.side_effect = KBServiceError(
            "Qdrant connection refused at localhost:6333"
        )

        response = client.post(
            "/knowledge/trust-settings/api-gateway/override",
            data={"trust_level": "trusted", "reason": "test reason"},
        )
        assert response.status_code == 500
        # Should show generic message, not internal details
        assert b"Failed to update trust level" in response.data
        assert b"localhost:6333" not in response.data


# ── KB Index Trust Settings Link Test ──


class TestKBIndexTrustLink:
    """Tests for Trust Settings link on KB index page.

    Task 6.3 (Jinja retirement, D13/D14): the KB index page (and its "Trust
    Settings" link) is now rendered by the React app — `GET /knowledge/`
    302-redirects to `/app/knowledge` before the Jinja view ever runs. This
    Python test can no longer assert on that specific link's presence; it
    now proves the redirect happens instead.
    """

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_index_has_trust_settings_link(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.list_entries.return_value = ([], 0)
        mock_svc.get_available_services.return_value = []
        mock_svc.get_available_entry_types.return_value = []

        response = client.get("/knowledge/")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/knowledge"
