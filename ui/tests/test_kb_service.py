"""Tests for the Knowledge Base service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError
from beeper_ui.services.kb_service import (
    KBEntry,
    KBService,
    KBServiceError,
    parse_date_range,
)


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


class TestKBServiceFilterMetadata:
    """Tests for filter metadata retrieval and caching."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_available_services_caching(self, mock_client_class: MagicMock) -> None:
        """Test that get_available_services caches results."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_points = []
        for svc in ["api", "payments"]:
            point = MagicMock()
            point.id = f"point-{svc}"
            point.payload = {"service": svc}
            mock_points.append(point)

        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()

        # First call should hit Qdrant
        services1 = service.get_available_services()
        assert services1 == ["api", "payments"]
        assert mock_client.scroll.call_count == 1

        # Second call should use cache
        services2 = service.get_available_services()
        assert services2 == ["api", "payments"]
        assert mock_client.scroll.call_count == 1  # Still 1 - cached

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_entry_types_caching(self, mock_client_class: MagicMock) -> None:
        """Test that get_entry_types caches results."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_points = []
        for entry_type in ["investigation", "runbook"]:
            point = MagicMock()
            point.id = f"point-{entry_type}"
            point.payload = {"entry_type": entry_type}
            mock_points.append(point)

        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()

        # First call should hit Qdrant
        types1 = service.get_entry_types()
        assert "investigation" in types1
        assert "runbook" in types1

        # Second call should use cache
        types2 = service.get_entry_types()
        assert types1 == types2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_clear_filter_cache(self, mock_client_class: MagicMock) -> None:
        """Test clearing the filter metadata cache."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_points = [MagicMock(id="p1", payload={"service": "api"})]
        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()

        # First call
        service.get_available_services()
        assert mock_client.scroll.call_count == 1

        # Clear cache
        service.clear_filter_cache()

        # Next call should hit Qdrant again
        service.get_available_services()
        assert mock_client.scroll.call_count == 2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_entry_types_returns_known_types(self, mock_client_class: MagicMock) -> None:
        """Test that get_entry_types always includes known types even if not in Qdrant."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Empty collection
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        types = service.get_entry_types()

        # Should still return known types
        assert "investigation" in types
        assert "runbook" in types
        assert "correction" in types


class TestParseDateRange:
    """Tests for parse_date_range function."""

    def test_parse_empty_string(self) -> None:
        """Test that empty string returns None, None."""
        date_from, date_to = parse_date_range("")
        assert date_from is None
        assert date_to is None

    def test_parse_none(self) -> None:
        """Test that None returns None, None."""
        date_from, date_to = parse_date_range(None)  # type: ignore
        assert date_from is None
        assert date_to is None

    def test_parse_today(self) -> None:
        """Test parsing 'today' date range."""
        date_from, date_to = parse_date_range("today")

        assert date_from is not None
        assert date_to is not None
        assert date_from.tzinfo == timezone.utc
        assert date_to.tzinfo == timezone.utc
        assert date_from.date() == date_to.date()
        assert date_from.hour == 0
        assert date_to.hour == 23

    def test_parse_7d(self) -> None:
        """Test parsing '7d' date range."""
        date_from, date_to = parse_date_range("7d")

        assert date_from is not None
        assert date_to is not None
        # date_from should be 7 days before date_to
        delta = date_to.date() - date_from.date()
        assert delta.days == 7

    def test_parse_30d(self) -> None:
        """Test parsing '30d' date range."""
        date_from, date_to = parse_date_range("30d")

        assert date_from is not None
        assert date_to is not None
        delta = date_to.date() - date_from.date()
        assert delta.days == 30

    def test_parse_90d(self) -> None:
        """Test parsing '90d' date range."""
        date_from, date_to = parse_date_range("90d")

        assert date_from is not None
        assert date_to is not None
        delta = date_to.date() - date_from.date()
        assert delta.days == 90

    def test_parse_unknown_range(self) -> None:
        """Test that unknown range returns None, None."""
        date_from, date_to = parse_date_range("unknown")
        assert date_from is None
        assert date_to is None


class TestKBServiceWriteOperations:
    """Tests for write operations (create, update, duplicate check)."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_success(self, mock_client_class: MagicMock) -> None:
        """Test creating a new KB entry successfully."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.upsert.return_value = None

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entry_id = service.create_entry(
            title="Test Runbook",
            content="## Overview\n\nThis is a test runbook.",
            entry_type="runbook",
            service="payments",
            tags=["database", "timeout"],
            author="import",
            embedding_service=mock_embedding_service,
        )

        assert entry_id is not None
        assert len(entry_id) > 0
        mock_client.upsert.assert_called_once()
        mock_embedding_service.get_embedding.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_generates_embedding(self, mock_client_class: MagicMock) -> None:
        """Test that create_entry generates embedding from title and content."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.5] * 1536

        service = KBService()
        service.create_entry(
            title="My Title",
            content="My content here",
            entry_type="runbook",
            embedding_service=mock_embedding_service,
        )

        # Embedding should be generated from title + content
        call_args = mock_embedding_service.get_embedding.call_args
        embedded_text = call_args[0][0]
        assert "My Title" in embedded_text
        assert "My content" in embedded_text

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_clears_services_cache(self, mock_client_class: MagicMock) -> None:
        """Test that create_entry clears the services cache for new services."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()

        # Prime the cache
        service.get_available_services()
        assert service._services_cache is not None

        # Create entry should clear cache
        service.create_entry(
            title="Test",
            content="Content",
            entry_type="runbook",
            service="new-service",
            embedding_service=mock_embedding_service,
        )

        assert service._services_cache is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_error(self, mock_client_class: MagicMock) -> None:
        """Test create_entry handles errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.upsert.side_effect = Exception("Connection failed")

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        with pytest.raises(KBServiceError, match="Failed to create KB entry"):
            service.create_entry(
                title="Test",
                content="Content",
                entry_type="runbook",
                embedding_service=mock_embedding_service,
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_check_duplicate_found(self, mock_client_class: MagicMock) -> None:
        """Test duplicate detection when a matching entry exists."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-existing"
        mock_point.payload = {
            "entry_id": "kb-existing",
            "entry_type": "runbook",
            "title": "Database Runbook",
            "content": "Existing content",
            "service": "payments",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        duplicate = service.check_duplicate(
            title="Database Runbook",
            service="payments",
            entry_type="runbook",
        )

        assert duplicate is not None
        assert duplicate.entry_id == "kb-existing"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_check_duplicate_case_insensitive(self, mock_client_class: MagicMock) -> None:
        """Test duplicate detection is case-insensitive for titles."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-1",
            "entry_type": "runbook",
            "title": "DATABASE RUNBOOK",
            "service": "api",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        duplicate = service.check_duplicate(
            title="database runbook",  # lowercase
            service="api",
            entry_type="runbook",
        )

        assert duplicate is not None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_check_duplicate_not_found(self, mock_client_class: MagicMock) -> None:
        """Test duplicate detection when no matching entry exists."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        duplicate = service.check_duplicate(
            title="New Runbook",
            service="payments",
            entry_type="runbook",
        )

        assert duplicate is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_check_duplicate_different_title(self, mock_client_class: MagicMock) -> None:
        """Test duplicate not found when title differs."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-1",
            "entry_type": "runbook",
            "title": "Different Title",
            "service": "payments",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        duplicate = service.check_duplicate(
            title="My New Runbook",
            service="payments",
            entry_type="runbook",
        )

        assert duplicate is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_entry_success(self, mock_client_class: MagicMock) -> None:
        """Test updating an existing KB entry."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock getting the existing entry
        mock_point = MagicMock()
        mock_point.id = "point-existing"
        mock_point.payload = {
            "entry_id": "kb-existing",
            "entry_type": "runbook",
            "title": "Original Title",
            "content": "Original content",
            "service": "payments",
            "version": 1,
            "created_at": "2026-01-15T10:00:00Z",
        }
        mock_client.scroll.return_value = ([mock_point], None)
        mock_client.upsert.return_value = None

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        new_version = service.update_entry(
            entry_id="kb-existing",
            title="Updated Title",
            content="Updated content",
            embedding_service=mock_embedding_service,
        )

        assert new_version == 2
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_entry_not_found(self, mock_client_class: MagicMock) -> None:
        """Test updating a non-existent entry raises error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        mock_embedding_service = MagicMock()

        service = KBService()
        with pytest.raises(KBServiceError, match="Entry not found"):
            service.update_entry(
                entry_id="non-existent",
                title="New Title",
                content="New content",
                embedding_service=mock_embedding_service,
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_entry_increments_version(self, mock_client_class: MagicMock) -> None:
        """Test that update_entry increments the version number."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-1",
            "version": 5,
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        new_version = service.update_entry(
            entry_id="kb-1",
            content="Updated",
            embedding_service=mock_embedding_service,
        )

        assert new_version == 6

        # Verify the upsert was called with version 6
        call_args = mock_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args[1].get("points")
        assert points[0].payload["version"] == 6


class TestKBServiceDateFiltering:
    """Tests for date range filtering in KBService."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_recent_entries_with_date_range(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test listing entries with date range filter."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 31, tzinfo=timezone.utc)

        service.list_recent_entries(date_from=date_from, date_to=date_to)

        # Verify filter was applied
        call_args = mock_client.scroll.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        # Should have date filter
        assert len(filter_arg.must) == 1
        assert filter_arg.must[0].key == "created_at"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_recent_entries_with_all_filters(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test listing entries with all filters combined."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)

        service.list_recent_entries(
            entry_type="investigation",
            service="payments",
            date_from=date_from,
        )

        # Verify all filters were applied
        call_args = mock_client.scroll.call_args
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert len(filter_arg.must) == 3  # entry_type + service + date

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_search_semantic_with_date_range(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test semantic search with date range filter."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_results = MagicMock()
        mock_results.points = []
        mock_client.query_points.return_value = mock_results

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 31, tzinfo=timezone.utc)

        service.search_semantic(
            query="test query",
            date_from=date_from,
            date_to=date_to,
            embedding_service=mock_embedding_service,
        )

        # Verify date filter was passed
        call_args = mock_client.query_points.call_args
        filter_arg = call_args.kwargs.get("query_filter")
        assert filter_arg is not None
        assert len(filter_arg.must) == 1
        assert filter_arg.must[0].key == "created_at"
