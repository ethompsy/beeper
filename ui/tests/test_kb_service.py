"""Tests for the Knowledge Base service."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError
from beeper_ui.services.kb_service import KBEntry, KBService, KBServiceError


class TestKBEntry:
    """Tests for KBEntry dataclass."""

    def test_from_qdrant_minimal(self) -> None:
        """Test creating KBEntry from minimal Qdrant payload."""
        entry = KBEntry.from_qdrant("point-123", {})
        assert entry.id == "point-123"
        assert entry.entry_id == "point-123"
        assert entry.entry_type == "unknown"
        assert entry.title == "Untitled"
        assert entry.content == ""
        assert entry.service is None
        assert entry.version == 1

    def test_from_qdrant_full(self) -> None:
        """Test creating KBEntry from full Qdrant payload."""
        payload = {
            "entry_id": "kb-abc123",
            "entry_type": "investigation",
            "title": "Test Investigation",
            "content": "## Summary\n\nSome content",
            "service": "payments",
            "created_at": "2026-02-13T10:30:00Z",
            "updated_at": "2026-02-13T11:00:00Z",
            "author": "beeper",
            "version": 2,
            "tags": ["database", "timeout"],
        }
        entry = KBEntry.from_qdrant("point-456", payload)

        assert entry.id == "point-456"
        assert entry.entry_id == "kb-abc123"
        assert entry.entry_type == "investigation"
        assert entry.title == "Test Investigation"
        assert entry.content == "## Summary\n\nSome content"
        assert entry.service == "payments"
        assert entry.author == "beeper"
        assert entry.version == 2
        assert entry.tags == ["database", "timeout"]
        assert entry.created_at is not None
        assert entry.updated_at is not None

    def test_from_qdrant_invalid_date(self) -> None:
        """Test KBEntry handles invalid dates gracefully."""
        payload = {
            "entry_id": "kb-123",
            "created_at": "not-a-date",
            "updated_at": "also-invalid",
        }
        entry = KBEntry.from_qdrant("point-789", payload)
        assert entry.created_at is None
        assert entry.updated_at is None


class TestKBService:
    """Tests for KBService."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_recent_entries_success(self, mock_client_class: MagicMock) -> None:
        """Test listing recent entries successfully."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-1",
            "entry_type": "runbook",
            "title": "Test Runbook",
            "content": "Content here",
            "service": "api",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        # Execute
        service = KBService(host="localhost", port=6333)
        entries = service.list_recent_entries(limit=10)

        # Verify
        assert len(entries) == 1
        assert entries[0].entry_id == "kb-1"
        assert entries[0].title == "Test Runbook"
        mock_client.scroll.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_recent_entries_with_filters(self, mock_client_class: MagicMock) -> None:
        """Test listing entries with type and service filters."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        service.list_recent_entries(entry_type="investigation", service="payments")

        # Verify filter was applied
        call_args = mock_client.scroll.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        assert len(filter_arg.must) == 2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_recent_entries_error(self, mock_client_class: MagicMock) -> None:
        """Test listing entries handles errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Connection failed")

        service = KBService()
        with pytest.raises(KBServiceError, match="Failed to list KB entries"):
            service.list_recent_entries()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_entry_found(self, mock_client_class: MagicMock) -> None:
        """Test getting a single entry by ID."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-specific",
            "entry_type": "investigation",
            "title": "Specific Entry",
            "content": "Details",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        entry = service.get_entry("kb-specific")

        assert entry is not None
        assert entry.entry_id == "kb-specific"
        assert entry.title == "Specific Entry"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_entry_not_found(self, mock_client_class: MagicMock) -> None:
        """Test getting non-existent entry returns None."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        entry = service.get_entry("non-existent")

        assert entry is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_entries_by_service(self, mock_client_class: MagicMock) -> None:
        """Test listing entries filtered by service."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        service.list_entries_by_service("payments", limit=5)

        call_args = mock_client.scroll.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        # Should have service filter
        assert any(c.key == "service" for c in filter_arg.must)

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_related_entries(self, mock_client_class: MagicMock) -> None:
        """Test listing related entries excludes the original."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock points including the original entry
        mock_points = []
        for i in range(3):
            point = MagicMock()
            point.id = f"point-{i}"
            point.payload = {
                "entry_id": f"kb-{i}",
                "entry_type": "investigation",
                "title": f"Entry {i}",
                "service": "api",
            }
            mock_points.append(point)

        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()
        related = service.list_related_entries("kb-0", service="api", limit=5)

        # Should exclude kb-0 (the original)
        entry_ids = [e.entry_id for e in related]
        assert "kb-0" not in entry_ids
        assert len(related) == 2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_available_services(self, mock_client_class: MagicMock) -> None:
        """Test getting unique service names."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_points = []
        for svc in ["payments", "api", "payments", "auth"]:
            point = MagicMock()
            point.id = f"point-{svc}"
            point.payload = {"service": svc}
            mock_points.append(point)

        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()
        services = service.get_available_services()

        assert services == ["api", "auth", "payments"]  # Sorted

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_health_check_healthy(self, mock_client_class: MagicMock) -> None:
        """Test health check when Qdrant is healthy."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_collection.return_value = {}

        service = KBService()
        assert service.health_check() is True

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_health_check_unhealthy(self, mock_client_class: MagicMock) -> None:
        """Test health check when Qdrant is unavailable."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Connection refused")

        service = KBService()
        assert service.health_check() is False

    def test_get_entry_types(self) -> None:
        """Test getting known entry types."""
        service = KBService()
        types = service.get_entry_types()
        assert "investigation" in types
        assert "runbook" in types
        assert "correction" in types


class TestKBServiceSemanticSearch:
    """Tests for semantic search functionality."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_success(self, mock_client_class: MagicMock) -> None:
        """Test successful semantic search."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock search results
        mock_point1 = MagicMock()
        mock_point1.id = "point-1"
        mock_point1.score = 0.85
        mock_point1.payload = {
            "entry_id": "kb-1",
            "entry_type": "investigation",
            "title": "Database Timeout",
            "content": "Investigation details",
            "service": "payments",
        }

        mock_point2 = MagicMock()
        mock_point2.id = "point-2"
        mock_point2.score = 0.72
        mock_point2.payload = {
            "entry_id": "kb-2",
            "entry_type": "runbook",
            "title": "DB Connection Guide",
            "content": "How to debug",
            "service": "api",
        }

        mock_results = MagicMock()
        mock_results.points = [mock_point1, mock_point2]
        mock_client.query_points.return_value = mock_results

        # Mock embedding service
        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entries, has_exact_matches = service.search_semantic(
            query="database connection timeout",
            limit=10,
            embedding_service=mock_embedding_service,
        )

        assert len(entries) == 2
        assert entries[0].entry_id == "kb-1"
        assert entries[0].relevance_score == 0.85
        assert entries[1].entry_id == "kb-2"
        assert entries[1].relevance_score == 0.72
        assert has_exact_matches is True  # max_score >= 0.7

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_no_exact_matches(self, mock_client_class: MagicMock) -> None:
        """Test semantic search with no exact matches (low scores)."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.score = 0.55  # Below 0.7 threshold
        mock_point.payload = {
            "entry_id": "kb-1",
            "entry_type": "investigation",
            "title": "Related Topic",
            "content": "Some content",
        }

        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_client.query_points.return_value = mock_results

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entries, has_exact_matches = service.search_semantic(
            query="obscure query",
            embedding_service=mock_embedding_service,
        )

        assert len(entries) == 1
        assert has_exact_matches is False  # max_score < 0.7

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_with_filters(self, mock_client_class: MagicMock) -> None:
        """Test semantic search with type and service filters."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points.return_value = mock_results

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        service.search_semantic(
            query="test query",
            entry_type="runbook",
            service="payments",
            embedding_service=mock_embedding_service,
        )

        # Verify filter was passed
        call_args = mock_client.query_points.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("query_filter")
        assert filter_arg is not None
        assert len(filter_arg.must) == 2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_empty_query(self, mock_client_class: MagicMock) -> None:
        """Test semantic search with empty query returns empty results."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        service = KBService()
        entries, has_exact_matches = service.search_semantic(query="")

        assert entries == []
        assert has_exact_matches is True
        mock_client.query_points.assert_not_called()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_embedding_error(self, mock_client_class: MagicMock) -> None:
        """Test semantic search handles embedding errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.side_effect = EmbeddingServiceError("API error")

        service = KBService()
        with pytest.raises(KBServiceError, match="Search failed"):
            service.search_semantic(
                query="test query",
                embedding_service=mock_embedding_service,
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_qdrant_error(self, mock_client_class: MagicMock) -> None:
        """Test semantic search handles Qdrant errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.query_points.side_effect = Exception("Connection failed")

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        with pytest.raises(KBServiceError, match="Search failed"):
            service.search_semantic(
                query="test query",
                embedding_service=mock_embedding_service,
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_no_results(self, mock_client_class: MagicMock) -> None:
        """Test semantic search with no results."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points.return_value = mock_results

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entries, has_exact_matches = service.search_semantic(
            query="completely unrelated query",
            embedding_service=mock_embedding_service,
        )

        assert entries == []
        assert has_exact_matches is True  # No results = no "low score" situation

    def test_kb_entry_relevance_score_default(self) -> None:
        """Test KBEntry has relevance_score field with default None."""
        entry = KBEntry.from_qdrant("point-1", {"entry_id": "kb-1"})
        assert entry.relevance_score is None
