"""Tests for Beeper KB client and schemas.

Unit tests run without Qdrant. Integration tests require a running Qdrant instance.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.kb.client import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    INVESTIGATIONS_COLLECTION,
    KNOWLEDGE_COLLECTION,
    KBClient,
    get_kb_client,
)
from beeper_investigator.kb.schemas import (
    CollectionInfo,
    InvestigationEntry,
    InvestigationStatus,
    KnowledgeEntry,
    KnowledgeEntryType,
    SearchResult,
)

# =============================================================================
# Schema Validation Tests (Unit Tests)
# =============================================================================


class TestInvestigationEntry:
    """Tests for InvestigationEntry schema validation."""

    def test_valid_investigation_entry(self) -> None:
        """Test creating a valid investigation entry."""
        entry = InvestigationEntry(
            investigation_id="inv-001",
            status=InvestigationStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
            service="payments",
            title="Payment Service Issue",
        )
        assert entry.investigation_id == "inv-001"
        assert entry.status == "active"
        assert entry.service == "payments"

    def test_investigation_entry_with_all_fields(self) -> None:
        """Test investigation entry with all optional fields."""
        entry = InvestigationEntry(
            investigation_id="inv-002",
            status=InvestigationStatus.RESOLVED,
            started_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            service="orders",
            title="Order Processing Failure",
            root_cause="Database connection pool exhaustion",
            resolution="Increased pool size and added connection timeout",
        )
        assert entry.root_cause is not None
        assert entry.resolution is not None

    def test_investigation_status_enum(self) -> None:
        """Test all investigation status values."""
        for status in InvestigationStatus:
            entry = InvestigationEntry(
                investigation_id="test",
                status=status,
                started_at=datetime.now(timezone.utc),
                service="test",
            )
            assert entry.status in ["active", "resolved", "stale"]


class TestKnowledgeEntry:
    """Tests for KnowledgeEntry schema validation."""

    def test_valid_knowledge_entry(self) -> None:
        """Test creating a valid knowledge entry."""
        entry = KnowledgeEntry(
            entry_id="kb-001",
            entry_type=KnowledgeEntryType.RUNBOOK,
            service="api-gateway",
            created_at=datetime.now(timezone.utc),
            title="API Gateway Troubleshooting",
            content="# Runbook\n\nSteps to follow...",
        )
        assert entry.entry_id == "kb-001"
        assert entry.entry_type == "runbook"
        assert entry.version == 1  # Default value

    def test_knowledge_entry_types(self) -> None:
        """Test all knowledge entry type values."""
        for entry_type in KnowledgeEntryType:
            entry = KnowledgeEntry(
                entry_id="test",
                entry_type=entry_type,
                service="test",
                created_at=datetime.now(timezone.utc),
                title="Test Entry",
                content="Test content",
            )
            assert entry.entry_type in [
                "investigation", "runbook", "correction", "proven_fix",
            ]

    def test_proven_fix_entry_type(self) -> None:
        """Test KnowledgeEntryType.PROVEN_FIX value is 'proven_fix'."""
        assert KnowledgeEntryType.PROVEN_FIX.value == "proven_fix"
        entry = KnowledgeEntry(
            entry_id="kb-proven-001",
            entry_type=KnowledgeEntryType.PROVEN_FIX,
            service="payments",
            created_at=datetime.now(timezone.utc),
            title="Proven Fix: Connection Pool Exhaustion",
            content="Fix content",
        )
        assert entry.entry_type == "proven_fix"


class TestSearchResult:
    """Tests for SearchResult schema."""

    def test_search_result(self) -> None:
        """Test creating a search result."""
        result = SearchResult(
            id="point-123",
            score=0.95,
            payload={"title": "Test", "content": "Content"},
        )
        assert result.id == "point-123"
        assert result.score == 0.95
        assert result.payload["title"] == "Test"


class TestCollectionInfo:
    """Tests for CollectionInfo schema."""

    def test_collection_info(self) -> None:
        """Test creating collection info."""
        info = CollectionInfo(
            name="knowledge",
            vectors_count=100,
            points_count=100,
        )
        assert info.name == "knowledge"
        assert info.vectors_count == 100


# =============================================================================
# Client Configuration Tests (Unit Tests)
# =============================================================================


class TestKBClientConfig:
    """Tests for KBClient configuration."""

    def test_default_configuration(self) -> None:
        """Test client uses default configuration."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing env vars
            os.environ.pop("QDRANT_HOST", None)
            os.environ.pop("QDRANT_PORT", None)

            client = KBClient()
            assert client.host == DEFAULT_HOST
            assert client.port == DEFAULT_PORT

    def test_environment_configuration(self) -> None:
        """Test client reads from environment variables."""
        with patch.dict(
            os.environ,
            {"QDRANT_HOST": "qdrant.example.com", "QDRANT_PORT": "16333"},
        ):
            client = KBClient()
            assert client.host == "qdrant.example.com"
            assert client.port == 16333

    def test_explicit_configuration(self) -> None:
        """Test explicit configuration overrides environment."""
        with patch.dict(os.environ, {"QDRANT_HOST": "env-host"}):
            client = KBClient(host="explicit-host", port=9999)
            assert client.host == "explicit-host"
            assert client.port == 9999


class TestKBClientMocked:
    """Tests for KBClient with mocked Qdrant client."""

    def test_health_check_success(self) -> None:
        """Test health check returns True when Qdrant is healthy."""
        client = KBClient()
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.return_value = []
        client._client = mock_qdrant

        assert client.health_check() is True
        mock_qdrant.get_collections.assert_called_once()

    def test_health_check_failure(self) -> None:
        """Test health check returns False when Qdrant is unavailable."""
        client = KBClient()
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.side_effect = Exception("Connection refused")
        client._client = mock_qdrant

        assert client.health_check() is False

    def test_get_collection_info(self) -> None:
        """Test getting collection info."""
        client = KBClient()
        mock_qdrant = MagicMock()
        mock_info = MagicMock()
        mock_info.indexed_vectors_count = 42
        mock_info.points_count = 42
        mock_qdrant.get_collection.return_value = mock_info
        client._client = mock_qdrant

        info = client.get_collection_info("test-collection")
        assert info is not None
        assert info.vectors_count == 42

    def test_search_knowledge_with_filters(self) -> None:
        """Test searching knowledge with filters."""
        client = KBClient()
        mock_qdrant = MagicMock()
        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.score = 0.9
        mock_point.payload = {"title": "Test"}
        mock_response = MagicMock()
        mock_response.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_response
        client._client = mock_qdrant

        results = client.search_knowledge(
            query_vector=[0.1] * 1536,
            entry_type="runbook",
            service="payments",
        )

        assert len(results) == 1
        assert results[0].score == 0.9
        mock_qdrant.query_points.assert_called_once()

    def test_close_client(self) -> None:
        """Test closing the client."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        client.close()

        mock_qdrant.close.assert_called_once()
        assert client._client is None


class TestGlobalKBClient:
    """Tests for the global KB client singleton."""

    def test_get_kb_client_singleton(self) -> None:
        """Test that get_kb_client returns the same instance."""
        # Reset the global
        import beeper_investigator.kb.client as client_module

        client_module._kb_client = None

        client1 = get_kb_client()
        client2 = get_kb_client()
        assert client1 is client2

    def test_get_kb_client_thread_safe(self) -> None:
        """Test that get_kb_client is thread-safe."""
        import threading

        import beeper_investigator.kb.client as client_module

        client_module._kb_client = None
        clients: list[KBClient] = []
        errors: list[Exception] = []

        def get_client() -> None:
            try:
                clients.append(get_kb_client())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_client) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(clients) == 10
        # All should be the same instance
        assert all(c is clients[0] for c in clients)


# =============================================================================
# Integration Tests (require running Qdrant)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("QDRANT_HOST"),
    reason="Qdrant not available (set QDRANT_HOST to enable)",
)
class TestKBClientIntegration:
    """Integration tests requiring a running Qdrant instance."""

    def test_health_check_integration(self) -> None:
        """Test health check against real Qdrant."""
        client = KBClient()
        assert client.health_check() is True

    def test_collection_exists(self) -> None:
        """Test that expected collections exist."""
        client = KBClient()

        # These collections should exist after running init-collections.py
        for collection_name in [INVESTIGATIONS_COLLECTION, KNOWLEDGE_COLLECTION]:
            info = client.get_collection_info(collection_name)
            assert info is not None, f"Collection '{collection_name}' should exist"

    def test_search_returns_results(self) -> None:
        """Test that search returns results from seeded data."""
        client = KBClient()

        # Use a placeholder vector (same as seed script)
        import random

        random.seed(42)
        query_vector = [random.uniform(-1, 1) for _ in range(1536)]

        results = client.search_knowledge(query_vector, limit=5)
        # Should have results if seed-kb.sh was run
        assert isinstance(results, list)


# =============================================================================
# Bi-directional KB-Investigation Link Tests (Unit Tests)
# =============================================================================


class TestGetKBEntriesForInvestigation:
    """Tests for KBClient.get_kb_entries_for_investigation.

    This method searches using a 'should' filter so that entries are returned
    when the investigation is the source creator OR a contributing investigation.
    """

    def test_returns_entries_matching_source_investigation_id(self) -> None:
        """Entries where source_investigation_id matches are returned."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point = MagicMock()
        mock_point.id = "point-src-001"
        mock_point.payload = {
            "entry_id": "entry-001",
            "source_investigation_id": "inv-123",
            "contributing_investigations": [],
        }
        mock_qdrant.scroll.return_value = ([mock_point], None)

        results = client.get_kb_entries_for_investigation("inv-123")

        assert len(results) == 1
        assert results[0].id == "point-src-001"
        assert results[0].payload["source_investigation_id"] == "inv-123"
        assert results[0].score == 1.0

    def test_returns_entries_matching_contributing_investigations(self) -> None:
        """Entries where contributing_investigations contains the ID are returned."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point = MagicMock()
        mock_point.id = "point-contrib-001"
        mock_point.payload = {
            "entry_id": "entry-002",
            "source_investigation_id": "inv-other",
            "contributing_investigations": ["inv-456"],
        }
        mock_qdrant.scroll.return_value = ([mock_point], None)

        results = client.get_kb_entries_for_investigation("inv-456")

        assert len(results) == 1
        assert results[0].id == "point-contrib-001"

    def test_returns_multiple_entries(self) -> None:
        """Multiple linked entries are returned together."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point_a = MagicMock()
        mock_point_a.id = "point-a"
        mock_point_a.payload = {
            "entry_id": "entry-a",
            "source_investigation_id": "inv-789",
        }
        mock_point_b = MagicMock()
        mock_point_b.id = "point-b"
        mock_point_b.payload = {
            "entry_id": "entry-b",
            "contributing_investigations": ["inv-789"],
        }
        mock_qdrant.scroll.return_value = ([mock_point_a, mock_point_b], None)

        results = client.get_kb_entries_for_investigation("inv-789")

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"point-a", "point-b"}

    def test_returns_empty_list_when_no_matches(self) -> None:
        """Empty list returned when no entries link to the investigation."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_qdrant.scroll.return_value = ([], None)

        results = client.get_kb_entries_for_investigation("inv-nonexistent")

        assert results == []

    def test_uses_should_filter_with_both_conditions(self) -> None:
        """Scroll is called with a 'should' filter for both fields."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        client.get_kb_entries_for_investigation("inv-check")

        mock_qdrant.scroll.assert_called_once()
        call_kwargs = mock_qdrant.scroll.call_args
        scroll_filter = call_kwargs.kwargs.get(
            "scroll_filter"
        ) or call_kwargs[1].get("scroll_filter")
        if scroll_filter is None:
            # Positional args: collection_name is [0][0], scroll_filter may be kwarg
            scroll_filter = call_kwargs.kwargs.get("scroll_filter")

        assert scroll_filter is not None
        assert scroll_filter.should is not None
        assert len(scroll_filter.should) == 2

        field_keys = [cond.key for cond in scroll_filter.should]
        assert "source_investigation_id" in field_keys
        assert "contributing_investigations" in field_keys

    def test_scroll_called_with_correct_params(self) -> None:
        """Scroll uses knowledge collection, with_payload=True, with_vectors=False."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        client.get_kb_entries_for_investigation("inv-params")

        mock_qdrant.scroll.assert_called_once()
        call_kwargs = mock_qdrant.scroll.call_args.kwargs
        assert call_kwargs.get("collection_name") == KNOWLEDGE_COLLECTION or (
            mock_qdrant.scroll.call_args[0][0] == KNOWLEDGE_COLLECTION
        )
        assert call_kwargs.get("with_payload") is True
        assert call_kwargs.get("with_vectors") is False
        assert call_kwargs.get("limit") == 50

    def test_returns_empty_list_on_exception(self) -> None:
        """Gracefully returns empty list when scroll raises an exception."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.side_effect = Exception("Qdrant unavailable")

        results = client.get_kb_entries_for_investigation("inv-fail")

        assert results == []

    def test_handles_none_payload(self) -> None:
        """Points with None payload get empty dict in result."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point = MagicMock()
        mock_point.id = "point-none"
        mock_point.payload = None
        mock_qdrant.scroll.return_value = ([mock_point], None)

        results = client.get_kb_entries_for_investigation("inv-null")

        assert len(results) == 1
        assert results[0].payload == {}


class TestGetEntriesByInvestigationId:
    """Tests for KBClient.get_entries_by_investigation_id.

    This method searches using a 'must' filter on source_investigation_id only,
    returning entries created by a specific investigation.
    """

    def test_returns_entries_created_by_investigation(self) -> None:
        """Entries with matching source_investigation_id are returned."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point = MagicMock()
        mock_point.id = "point-created-001"
        mock_point.payload = {
            "entry_id": "entry-created-001",
            "source_investigation_id": "inv-src-001",
        }
        mock_qdrant.scroll.return_value = ([mock_point], None)

        results = client.get_entries_by_investigation_id("inv-src-001")

        assert len(results) == 1
        assert results[0].id == "point-created-001"
        assert results[0].payload["source_investigation_id"] == "inv-src-001"
        assert results[0].score == 1.0

    def test_returns_empty_list_when_no_matches(self) -> None:
        """Empty list returned when no entries were created by the investigation."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        results = client.get_entries_by_investigation_id("inv-no-entries")

        assert results == []

    def test_uses_must_filter_on_source_investigation_id(self) -> None:
        """Scroll is called with a 'must' filter on source_investigation_id."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        client.get_entries_by_investigation_id("inv-must-check")

        mock_qdrant.scroll.assert_called_once()
        call_kwargs = mock_qdrant.scroll.call_args
        scroll_filter = call_kwargs.kwargs.get(
            "scroll_filter"
        ) or call_kwargs[1].get("scroll_filter")

        assert scroll_filter is not None
        assert scroll_filter.must is not None
        assert len(scroll_filter.must) == 1
        assert scroll_filter.must[0].key == "source_investigation_id"
        assert scroll_filter.must[0].match.value == "inv-must-check"

    def test_does_not_use_should_filter(self) -> None:
        """Unlike get_kb_entries_for_investigation, this uses must not should."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        client.get_entries_by_investigation_id("inv-no-should")

        call_kwargs = mock_qdrant.scroll.call_args
        scroll_filter = call_kwargs.kwargs.get(
            "scroll_filter"
        ) or call_kwargs[1].get("scroll_filter")

        # should is None or empty
        assert not scroll_filter.should

    def test_returns_multiple_entries(self) -> None:
        """An investigation can create multiple KB entries."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        points = []
        for i in range(3):
            p = MagicMock()
            p.id = f"point-multi-{i}"
            p.payload = {
                "entry_id": f"entry-multi-{i}",
                "source_investigation_id": "inv-multi",
            }
            points.append(p)
        mock_qdrant.scroll.return_value = (points, None)

        results = client.get_entries_by_investigation_id("inv-multi")

        assert len(results) == 3

    def test_returns_empty_list_on_exception(self) -> None:
        """Gracefully returns empty list when scroll raises an exception."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.side_effect = Exception("Qdrant connection lost")

        results = client.get_entries_by_investigation_id("inv-error")

        assert results == []

    def test_scroll_called_with_correct_params(self) -> None:
        """Scroll uses knowledge collection, correct limit, payload and vector flags."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant
        mock_qdrant.scroll.return_value = ([], None)

        client.get_entries_by_investigation_id("inv-params-check")

        mock_qdrant.scroll.assert_called_once()
        call_kwargs = mock_qdrant.scroll.call_args.kwargs
        assert call_kwargs.get("collection_name") == KNOWLEDGE_COLLECTION or (
            mock_qdrant.scroll.call_args[0][0] == KNOWLEDGE_COLLECTION
        )
        assert call_kwargs.get("with_payload") is True
        assert call_kwargs.get("with_vectors") is False
        assert call_kwargs.get("limit") == 50

    def test_handles_none_payload(self) -> None:
        """Points with None payload get empty dict in result."""
        client = KBClient()
        mock_qdrant = MagicMock()
        client._client = mock_qdrant

        mock_point = MagicMock()
        mock_point.id = "point-null-payload"
        mock_point.payload = None
        mock_qdrant.scroll.return_value = ([mock_point], None)

        results = client.get_entries_by_investigation_id("inv-null-payload")

        assert len(results) == 1
        assert results[0].payload == {}
