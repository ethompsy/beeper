"""Tests for the Knowledge Base service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError
from beeper_ui.services.kb_service import (
    KBEntry,
    KBService,
    KBServiceError,
    generate_diff,
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
        # 2 upsert calls: knowledge entry + version snapshot
        assert mock_client.upsert.call_count == 2
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
        # 2 upsert calls: version snapshot + knowledge update
        assert mock_client.upsert.call_count == 2

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


class TestKBServiceVersionHistory:
    """Tests for version history methods."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_save_version_snapshot_stores_correct_data(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test _save_version_snapshot stores current entry state."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        service = KBService()
        payload = {
            "entry_id": "kb-abc123",
            "version": 2,
            "title": "Test Title",
            "content": "Test content",
            "author": "edit",
            "created_at": "2026-02-17T10:00:00Z",
            "updated_at": "2026-02-17T11:00:00Z",
            "entry_type": "runbook",
            "service": "api",
            "tags": ["tag1", "tag2"],
        }

        service._save_version_snapshot(
            entry_id="kb-abc123", payload=payload, point_id="point-1"
        )

        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "knowledge_versions"
        point = call_args.kwargs["points"][0]
        assert point.payload["entry_id"] == "kb-abc123"
        assert point.payload["version"] == 2
        assert point.payload["title"] == "Test Title"
        assert point.payload["content"] == "Test content"
        assert point.vector == [0.0]

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_list_versions_returns_ordered(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test list_versions returns versions in descending order with extra fields."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_points = []
        for v in [1, 3, 2]:
            point = MagicMock()
            point.id = f"point-v{v}"
            point.payload = {
                "entry_id": "kb-abc123",
                "version": v,
                "author": "edit",
                "updated_at": f"2026-02-1{v}T10:00:00Z",
                "title": f"Title v{v}",
                "content": f"Content v{v}",
                "tags": ["tag1"],
                "service": "api",
            }
            mock_points.append(point)

        mock_client.scroll.return_value = (mock_points, None)

        service = KBService()
        versions = service.list_versions("kb-abc123")

        assert len(versions) == 3
        assert versions[0]["version"] == 3
        assert versions[1]["version"] == 2
        assert versions[2]["version"] == 1
        # Verify extra fields for change summary computation
        assert versions[0]["content_length"] == len("Content v3")
        assert versions[0]["tags"] == ["tag1"]
        assert versions[0]["service"] == "api"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_version_returns_correct_content(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test get_version returns correct version content."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-v2"
        mock_point.payload = {
            "entry_id": "kb-abc123",
            "version": 2,
            "title": "Title v2",
            "content": "Content at version 2",
            "author": "edit",
            "entry_type": "runbook",
            "service": "api",
            "tags": ["tag1"],
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        version = service.get_version("kb-abc123", 2)

        assert version is not None
        assert version["version"] == 2
        assert version["title"] == "Title v2"
        assert version["content"] == "Content at version 2"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_version_not_found(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test get_version returns None for missing version."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        version = service.get_version("kb-abc123", 99)

        assert version is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_entry_saves_snapshot_before_overwrite(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test update_entry saves snapshot before overwriting."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

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
            "updated_at": "2026-01-15T10:00:00Z",
            "author": "import",
            "tags": [],
        }
        mock_client.scroll.return_value = ([mock_point], None)
        mock_client.upsert.return_value = None

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        new_version = service.update_entry(
            entry_id="kb-existing",
            title="Updated Title",
            embedding_service=mock_embedding_service,
        )

        assert new_version == 2
        # Two upsert calls: one for version snapshot, one for the actual update
        assert mock_client.upsert.call_count == 2
        # First call should be to knowledge_versions
        first_call = mock_client.upsert.call_args_list[0]
        assert first_call.kwargs["collection_name"] == "knowledge_versions"
        snapshot_payload = first_call.kwargs["points"][0].payload
        assert snapshot_payload["version"] == 1
        assert snapshot_payload["title"] == "Original Title"
        # Second call should be to knowledge
        second_call = mock_client.upsert.call_args_list[1]
        assert second_call.kwargs["collection_name"] == "knowledge"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_saves_initial_version_snapshot(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test create_entry saves version 1 snapshot."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.upsert.return_value = None

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entry_id = service.create_entry(
            title="New Entry",
            content="New content here",
            entry_type="runbook",
            service="api",
            tags=["tag1"],
            author="import",
            embedding_service=mock_embedding_service,
        )

        assert entry_id is not None
        # Two upsert calls: one to knowledge, one to knowledge_versions
        assert mock_client.upsert.call_count == 2
        # First call is the main entry (knowledge collection)
        first_call = mock_client.upsert.call_args_list[0]
        assert first_call.kwargs["collection_name"] == "knowledge"
        # Second call is the version snapshot (knowledge_versions)
        second_call = mock_client.upsert.call_args_list[1]
        assert second_call.kwargs["collection_name"] == "knowledge_versions"
        snapshot_payload = second_call.kwargs["points"][0].payload
        assert snapshot_payload["version"] == 1
        assert snapshot_payload["title"] == "New Entry"


    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_entry_snapshot_failure_non_fatal(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test create_entry succeeds even if initial version snapshot fails."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # First upsert (main entry) succeeds, second (snapshot) fails
        mock_client.upsert.side_effect = [None, Exception("Snapshot failed")]

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        entry_id = service.create_entry(
            title="Test Entry",
            content="Test content here",
            entry_type="runbook",
            service="api",
            embedding_service=mock_embedding_service,
        )

        # Entry should still be created successfully
        assert entry_id is not None
        assert len(entry_id) > 0
        assert mock_client.upsert.call_count == 2


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


class TestGenerateDiff:
    """Tests for generate_diff function."""

    def test_additions_only(self) -> None:
        """Test diff with content additions."""
        old = "line 1\nline 2"
        new = "line 1\nline 2\nline 3\nline 4"
        result = generate_diff(old, new)

        assert result["has_changes"] is True
        assert "2 additions" in result["summary"]
        added = [
            ln for h in result["hunks"] for ln in h["lines"] if ln["type"] == "add"
        ]
        assert len(added) == 2
        assert added[0]["content"] == "line 3"
        assert added[1]["content"] == "line 4"

    def test_deletions_only(self) -> None:
        """Test diff with content deletions."""
        old = "line 1\nline 2\nline 3"
        new = "line 1"
        result = generate_diff(old, new)

        assert result["has_changes"] is True
        assert "2 deletions" in result["summary"]
        removed = [
            ln for h in result["hunks"] for ln in h["lines"] if ln["type"] == "remove"
        ]
        assert len(removed) == 2

    def test_mixed_changes(self) -> None:
        """Test diff with both additions and deletions."""
        old = "line 1\nold line 2\nline 3"
        new = "line 1\nnew line 2\nline 3"
        result = generate_diff(old, new)

        assert result["has_changes"] is True
        assert "addition" in result["summary"]
        assert "deletion" in result["summary"]

    def test_identical_content(self) -> None:
        """Test diff with identical content returns no changes."""
        content = "line 1\nline 2\nline 3"
        result = generate_diff(content, content)

        assert result["has_changes"] is False
        assert result["hunks"] == []
        assert result["summary"] == "No changes"

    def test_empty_to_content(self) -> None:
        """Test diff from empty to content."""
        result = generate_diff("", "line 1\nline 2")

        assert result["has_changes"] is True
        assert "2 additions" in result["summary"]

    def test_content_to_empty(self) -> None:
        """Test diff from content to empty."""
        result = generate_diff("line 1\nline 2", "")

        assert result["has_changes"] is True
        assert "2 deletions" in result["summary"]

    def test_both_empty(self) -> None:
        """Test diff with both contents empty."""
        result = generate_diff("", "")

        assert result["has_changes"] is False

    def test_line_numbers_correct(self) -> None:
        """Test that line numbers are correctly assigned."""
        old = "a\nb\nc"
        new = "a\nx\nc"
        result = generate_diff(old, new)

        assert result["has_changes"] is True
        for hunk in result["hunks"]:
            for ln in hunk["lines"]:
                if ln["type"] == "add":
                    assert ln["old_num"] is None
                    assert ln["new_num"] is not None
                elif ln["type"] == "remove":
                    assert ln["old_num"] is not None
                    assert ln["new_num"] is None
                elif ln["type"] == "context":
                    assert ln["old_num"] is not None
                    assert ln["new_num"] is not None

    def test_hunk_header_present(self) -> None:
        """Test that each hunk has a header."""
        old = "line 1\nline 2"
        new = "line 1\nchanged"
        result = generate_diff(old, new)

        assert len(result["hunks"]) > 0
        for hunk in result["hunks"]:
            assert hunk["header"].startswith("@@")

    def test_singular_summary(self) -> None:
        """Test summary uses singular form for single change."""
        old = "line 1"
        new = "line 1\nline 2"
        result = generate_diff(old, new)

        assert "1 addition" in result["summary"]
        assert "additions" not in result["summary"]

    def test_content_with_markdown_horizontal_rule(self) -> None:
        """Test diff correctly handles content containing --- (markdown HR)."""
        old = "title\n---\ncontent"
        new = "title\ncontent"
        result = generate_diff(old, new)

        assert result["has_changes"] is True
        removed = [
            ln for h in result["hunks"] for ln in h["lines"] if ln["type"] == "remove"
        ]
        assert any(ln["content"] == "---" for ln in removed)


class TestGetSourceInvestigation:
    """Tests for get_source_investigation method."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_source_when_present(self, mock_client_class: MagicMock) -> None:
        """Test with entry that has source_investigation_id set."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-abc",
            "source_investigation_id": "inv-source-123",
            "contributing_investigations": ["inv-contrib-1"],
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_source_investigation("kb-abc")

        assert result is not None
        assert result["investigation_id"] == "inv-source-123"
        assert result["relationship"] == "source"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_none_when_no_source(self, mock_client_class: MagicMock) -> None:
        """Test with entry without source_investigation_id."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-no-source",
            "title": "No Source Entry",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_source_investigation("kb-no-source")

        assert result is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_none_when_entry_not_found(self, mock_client_class: MagicMock) -> None:
        """Test returns None when entry does not exist."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        result = service.get_source_investigation("kb-nonexistent")

        assert result is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_none_when_source_id_empty(self, mock_client_class: MagicMock) -> None:
        """Test returns None when source_investigation_id is empty string."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-empty-source",
            "source_investigation_id": "",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_source_investigation("kb-empty-source")

        assert result is None


class TestGetContributingInvestigations:
    """Tests for get_contributing_investigations method."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_contributing_list(self, mock_client_class: MagicMock) -> None:
        """Test with entry that has contributing_investigations list."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-contribs",
            "source_investigation_id": "inv-source-1",
            "contributing_investigations": [
                "inv-source-1",
                "inv-contrib-2",
                "inv-contrib-3",
            ],
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_contributing_investigations("kb-contribs")

        # Should exclude source_investigation_id from results
        assert len(result) == 2
        inv_ids = [r["investigation_id"] for r in result]
        assert "inv-contrib-2" in inv_ids
        assert "inv-contrib-3" in inv_ids
        assert "inv-source-1" not in inv_ids
        for item in result:
            assert item["relationship"] == "contributing"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_empty_when_no_contribs(self, mock_client_class: MagicMock) -> None:
        """Test returns empty list when no contributing_investigations."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-no-contribs",
            "title": "No Contribs",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_contributing_investigations("kb-no-contribs")

        assert result == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_empty_when_entry_not_found(self, mock_client_class: MagicMock) -> None:
        """Test returns empty list when entry does not exist."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        result = service.get_contributing_investigations("kb-nonexistent")

        assert result == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_excludes_source_from_contribs(self, mock_client_class: MagicMock) -> None:
        """Test that source_investigation_id is excluded from contributing list."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-overlap",
            "source_investigation_id": "inv-overlap",
            "contributing_investigations": ["inv-overlap", "inv-other"],
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService()
        result = service.get_contributing_investigations("kb-overlap")

        assert len(result) == 1
        assert result[0]["investigation_id"] == "inv-other"
        assert result[0]["relationship"] == "contributing"


class TestGetLinkedKBEntries:
    """Tests for get_linked_kb_entries method."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_linked_entries(self, mock_client_class: MagicMock) -> None:
        """Test returns KBEntry list for matching investigation_id."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point1 = MagicMock()
        mock_point1.id = "point-1"
        mock_point1.payload = {
            "entry_id": "kb-linked-1",
            "entry_type": "investigation",
            "title": "Linked Entry 1",
            "content": "Content 1",
            "service": "payments",
            "source_investigation_id": "inv-abc",
        }

        mock_point2 = MagicMock()
        mock_point2.id = "point-2"
        mock_point2.payload = {
            "entry_id": "kb-linked-2",
            "entry_type": "runbook",
            "title": "Linked Entry 2",
            "content": "Content 2",
            "service": "api",
            "contributing_investigations": ["inv-abc"],
        }
        mock_client.scroll.return_value = ([mock_point1, mock_point2], None)

        service = KBService()
        result = service.get_linked_kb_entries("inv-abc")

        assert len(result) == 2
        assert isinstance(result[0], KBEntry)
        assert isinstance(result[1], KBEntry)
        assert result[0].entry_id == "kb-linked-1"
        assert result[1].entry_id == "kb-linked-2"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_empty_when_no_matches(self, mock_client_class: MagicMock) -> None:
        """Test returns empty list when no matches found."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        result = service.get_linked_kb_entries("inv-no-links")

        assert result == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_empty_on_error(self, mock_client_class: MagicMock) -> None:
        """Test returns empty list when Qdrant raises an error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Connection failed")

        service = KBService()
        result = service.get_linked_kb_entries("inv-error")

        assert result == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_uses_should_filter(self, mock_client_class: MagicMock) -> None:
        """Test that scroll uses should filter for source or contributing."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService()
        service.get_linked_kb_entries("inv-filter-test")

        call_args = mock_client.scroll.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        # Should use 'should' (OR) filter, not 'must' (AND)
        assert filter_arg.should is not None
        assert len(filter_arg.should) == 2


class TestLinkPreservationOnUpdate:
    """Tests for verifying update_entry preserves bi-directional link fields."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_preserves_source_investigation_id(self, mock_client_class: MagicMock) -> None:
        """Test that update_entry preserves source_investigation_id in the payload."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-preserve",
            "entry_type": "investigation",
            "title": "Original",
            "content": "Original content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "source_investigation_id": "inv-source-999",
            "contributing_investigations": ["inv-contrib-1", "inv-contrib-2"],
            "linked_investigations": ["inv-linked-1"],
            "validation_status": "validated",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        service.update_entry(
            entry_id="kb-preserve",
            title="Updated Title",
            embedding_service=mock_embedding_service,
        )

        # Get the upsert call for the knowledge update (last call)
        upsert_calls = mock_client.upsert.call_args_list
        # Last upsert is the knowledge entry update
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload

        assert payload["source_investigation_id"] == "inv-source-999"
        assert payload["contributing_investigations"] == ["inv-contrib-1", "inv-contrib-2"]
        assert payload["linked_investigations"] == ["inv-linked-1"]
        assert payload["validation_status"] == "validated"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_preserves_empty_link_fields(self, mock_client_class: MagicMock) -> None:
        """Test that update_entry preserves link fields even when they are empty/None."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-2"
        mock_point.payload = {
            "entry_id": "kb-no-links",
            "entry_type": "runbook",
            "title": "No Links",
            "content": "Content without links",
            "version": 3,
            "created_at": "2026-01-15T00:00:00Z",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        service.update_entry(
            entry_id="kb-no-links",
            content="Updated content",
            embedding_service=mock_embedding_service,
        )

        # Get the knowledge update upsert (last call)
        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload

        # Fields should still be present in payload (with defaults)
        assert "source_investigation_id" in payload
        assert "contributing_investigations" in payload
        assert "linked_investigations" in payload
        assert "validation_status" in payload
        assert payload["contributing_investigations"] == []
        assert payload["linked_investigations"] == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_link_fields_survive_title_update(self, mock_client_class: MagicMock) -> None:
        """Test that updating only title does not lose link fields."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-3"
        mock_point.payload = {
            "entry_id": "kb-title-update",
            "entry_type": "investigation",
            "title": "Old Title",
            "content": "Existing content",
            "version": 2,
            "created_at": "2026-02-01T00:00:00Z",
            "source_investigation_id": "inv-keep-this",
            "contributing_investigations": ["inv-keep-too"],
            "linked_investigations": ["inv-also-keep"],
            "validation_status": "pending",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService()
        new_version = service.update_entry(
            entry_id="kb-title-update",
            title="New Title Only",
            embedding_service=mock_embedding_service,
        )

        assert new_version == 3

        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload

        # Title should be updated
        assert payload["title"] == "New Title Only"
        # Content should be preserved
        assert payload["content"] == "Existing content"
        # All link fields should be preserved
        assert payload["source_investigation_id"] == "inv-keep-this"
        assert payload["contributing_investigations"] == ["inv-keep-too"]
        assert payload["linked_investigations"] == ["inv-also-keep"]
        assert payload["validation_status"] == "pending"


class TestGetServiceKnowledgeGrouped:
    """Tests for KBService.get_service_knowledge_grouped()."""

    def _make_point(
        self,
        entry_id: str,
        entry_type: str,
        service: str,
        validation_status: str = "AI-generated",
    ) -> MagicMock:
        """Create a mock Qdrant point."""
        point = MagicMock()
        point.id = f"point-{entry_id}"
        point.payload = {
            "entry_id": entry_id,
            "entry_type": entry_type,
            "title": f"Entry {entry_id}",
            "content": "Content",
            "service": service,
            "created_at": "2026-03-17T10:00:00Z",
            "validation_status": validation_status,
        }
        return point

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_groups_entries_by_type(self, mock_client_class: MagicMock) -> None:
        """Test entries are correctly grouped by entry_type."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        points = [
            self._make_point("kb-1", "investigation", "api"),
            self._make_point("kb-2", "runbook", "api"),
            self._make_point("kb-3", "proven_fix", "api"),
            self._make_point("kb-4", "correction", "api"),
            self._make_point("kb-5", "investigation", "api"),
        ]
        mock_client.scroll.return_value = (points, None)

        service = KBService(host="localhost", port=6333)
        groups = service.get_service_knowledge_grouped("api")

        assert len(groups["root_causes"]) == 2
        assert len(groups["runbooks"]) == 1
        assert len(groups["proven_fixes"]) == 1
        assert len(groups["patterns"]) == 1

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_filters_by_service_name(self, mock_client_class: MagicMock) -> None:
        """Test that service name filter is applied in query."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService(host="localhost", port=6333)
        service.get_service_knowledge_grouped("payment-service")

        call_args = mock_client.scroll.call_args
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        assert len(filter_arg.must) == 1
        assert filter_arg.must[0].key == "service"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_filters_by_validation_status(self, mock_client_class: MagicMock) -> None:
        """Test that validation_status filter is applied when provided."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService(host="localhost", port=6333)
        service.get_service_knowledge_grouped("api", validation_status="proven")

        call_args = mock_client.scroll.call_args
        filter_arg = call_args.kwargs.get("scroll_filter")
        assert filter_arg is not None
        assert len(filter_arg.must) == 2

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_empty_groups_when_no_entries(self, mock_client_class: MagicMock) -> None:
        """Test returns empty group lists when no entries exist."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService(host="localhost", port=6333)
        groups = service.get_service_knowledge_grouped("empty-service")

        assert groups["root_causes"] == []
        assert groups["runbooks"] == []
        assert groups["proven_fixes"] == []
        assert groups["patterns"] == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_unknown_type_goes_to_patterns(self, mock_client_class: MagicMock) -> None:
        """Test that unknown entry types are grouped under patterns."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        points = [self._make_point("kb-1", "custom_type", "api")]
        mock_client.scroll.return_value = (points, None)

        service = KBService(host="localhost", port=6333)
        groups = service.get_service_knowledge_grouped("api")

        assert len(groups["patterns"]) == 1
        assert groups["patterns"][0].entry_type == "custom_type"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_raises_on_error(self, mock_client_class: MagicMock) -> None:
        """Test raises KBServiceError on failure."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Connection failed")

        service = KBService(host="localhost", port=6333)
        with pytest.raises(KBServiceError, match="Failed to get service knowledge"):
            service.get_service_knowledge_grouped("api")


class TestGetServiceValidationCounts:
    """Tests for KBService.get_service_validation_counts()."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_counts_entries_per_status(self, mock_client_class: MagicMock) -> None:
        """Test counts entries correctly per validation_status."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        points = []
        statuses = ["AI-generated", "AI-generated", "proven", "human-confirmed", "AI-generated"]
        for i, status in enumerate(statuses):
            point = MagicMock()
            point.id = f"point-{i}"
            point.payload = {"validation_status": status}
            points.append(point)
        mock_client.scroll.return_value = (points, None)

        service = KBService(host="localhost", port=6333)
        counts = service.get_service_validation_counts("api")

        assert counts["AI-generated"] == 3
        assert counts["proven"] == 1
        assert counts["human-confirmed"] == 1
        assert counts["total"] == 5

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_returns_total_count(self, mock_client_class: MagicMock) -> None:
        """Test total count matches sum of entries."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-1"
        point.payload = {"validation_status": "proven"}
        mock_client.scroll.return_value = ([point], None)

        service = KBService(host="localhost", port=6333)
        counts = service.get_service_validation_counts("api")

        assert counts["total"] == 1
        assert counts["proven"] == 1

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_empty_for_no_entries(self, mock_client_class: MagicMock) -> None:
        """Test returns only total=0 for service with no entries."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService(host="localhost", port=6333)
        counts = service.get_service_validation_counts("empty-service")

        assert counts["total"] == 0

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_handles_missing_validation_status(self, mock_client_class: MagicMock) -> None:
        """Test entries with no validation_status counted as 'unknown'."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-1"
        point.payload = {}
        mock_client.scroll.return_value = ([point], None)

        service = KBService(host="localhost", port=6333)
        counts = service.get_service_validation_counts("api")

        assert counts["unknown"] == 1
        assert counts["total"] == 1

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_handles_none_validation_status(self, mock_client_class: MagicMock) -> None:
        """Test entries with None validation_status counted as 'unknown'."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-1"
        point.payload = {"validation_status": None}
        mock_client.scroll.return_value = ([point], None)

        service = KBService(host="localhost", port=6333)
        counts = service.get_service_validation_counts("api")

        assert counts["unknown"] == 1
        assert counts["total"] == 1

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_raises_on_error(self, mock_client_class: MagicMock) -> None:
        """Test raises KBServiceError on failure."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Connection failed")

        service = KBService(host="localhost", port=6333)
        with pytest.raises(KBServiceError, match="Failed to get validation counts"):
            service.get_service_validation_counts("api")


class TestConfirmEntry:
    """Tests for KBService.confirm_entry() method."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_successful_confirmation(self, mock_client_class: MagicMock) -> None:
        """Test confirming an AI-generated entry changes status to human-confirmed."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {
            "entry_id": "kb-confirm-1",
            "entry_type": "investigation",
            "title": "Test Entry",
            "content": "Some content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "validation_status": "AI-generated",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService(host="localhost", port=6333)
        new_version = service.confirm_entry("kb-confirm-1", "sre-sam")

        assert new_version == 2

        # Check the upsert call for knowledge entry
        upsert_calls = mock_client.upsert.call_args_list
        # Last upsert is the knowledge entry update (first is version snapshot)
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload

        assert payload["validation_status"] == "human-confirmed"
        assert payload["version"] == 2
        assert payload["author"] == "sre-sam"
        assert "updated_at" in payload

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_saves_version_snapshot(self, mock_client_class: MagicMock) -> None:
        """Test that version snapshot is saved before confirmation."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {
            "entry_id": "kb-snap",
            "entry_type": "investigation",
            "title": "Title",
            "content": "Content",
            "version": 3,
            "created_at": "2026-01-01T00:00:00Z",
            "validation_status": "AI-generated",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService(host="localhost", port=6333)
        service.confirm_entry("kb-snap", "user")

        # Should have 2 upsert calls: version snapshot + knowledge entry update
        assert mock_client.upsert.call_count == 2
        # First upsert is the version snapshot (to knowledge_versions)
        first_call = mock_client.upsert.call_args_list[0]
        collection = first_call.kwargs.get("collection_name") or first_call[1].get(
            "collection_name"
        )
        assert collection == "knowledge_versions"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_rejects_non_ai_generated(self, mock_client_class: MagicMock) -> None:
        """Test that confirming a non-AI-generated entry raises an error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {
            "entry_id": "kb-proven",
            "validation_status": "proven",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService(host="localhost", port=6333)
        with pytest.raises(KBServiceError, match="Can only confirm AI-generated"):
            service.confirm_entry("kb-proven", "user")

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_entry_not_found(self, mock_client_class: MagicMock) -> None:
        """Test confirming a nonexistent entry raises an error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        service = KBService(host="localhost", port=6333)
        with pytest.raises(KBServiceError, match="KB entry not found"):
            service.confirm_entry("kb-missing", "user")

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_rejects_none_validation_status(self, mock_client_class: MagicMock) -> None:
        """Test confirming a legacy entry with validation_status=None raises an error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {
            "entry_id": "kb-legacy",
            "entry_type": "investigation",
            "title": "Legacy Entry",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        service = KBService(host="localhost", port=6333)
        with pytest.raises(KBServiceError, match="Can only confirm AI-generated"):
            service.confirm_entry("kb-legacy", "user")


class TestUpdateEntryValidationStatus:
    """Tests for update_entry with validation_status parameter."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_sets_validation_status_when_provided(self, mock_client_class: MagicMock) -> None:
        """Test that passing validation_status updates the field."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-edit",
            "entry_type": "investigation",
            "title": "Old Title",
            "content": "Old content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "validation_status": "AI-generated",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService(host="localhost", port=6333)
        service.update_entry(
            entry_id="kb-edit",
            content="Corrected content",
            embedding_service=mock_embedding_service,
            validation_status="corrected",
        )

        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload
        assert payload["validation_status"] == "corrected"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_preserves_status_when_not_provided(self, mock_client_class: MagicMock) -> None:
        """Test that omitting validation_status preserves existing value."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-tags-only",
            "entry_type": "investigation",
            "title": "Title",
            "content": "Content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "validation_status": "human-confirmed",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService(host="localhost", port=6333)
        service.update_entry(
            entry_id="kb-tags-only",
            tags=["new-tag"],
            embedding_service=mock_embedding_service,
        )

        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload
        assert payload["validation_status"] == "human-confirmed"


class TestUpdateEntryEntryType:
    """Tests for update_entry with entry_type parameter."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_sets_entry_type_when_provided(self, mock_client_class: MagicMock) -> None:
        """Test that passing entry_type updates the field in the payload."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-cat-change",
            "entry_type": "investigation",
            "title": "Title",
            "content": "Content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService(host="localhost", port=6333)
        service.update_entry(
            entry_id="kb-cat-change",
            embedding_service=mock_embedding_service,
            entry_type="runbook",
        )

        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload
        assert payload["entry_type"] == "runbook"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_preserves_entry_type_when_not_provided(self, mock_client_class: MagicMock) -> None:
        """Test that omitting entry_type preserves existing value."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "entry_id": "kb-cat-keep",
            "entry_type": "proven_fix",
            "title": "Title",
            "content": "Content",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_client.scroll.return_value = ([mock_point], None)

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1536

        service = KBService(host="localhost", port=6333)
        service.update_entry(
            entry_id="kb-cat-keep",
            tags=["updated-tag"],
            embedding_service=mock_embedding_service,
        )

        upsert_calls = mock_client.upsert.call_args_list
        last_call = upsert_calls[-1]
        points = last_call.kwargs.get("points") or last_call[1].get("points")
        payload = points[0].payload
        assert payload["entry_type"] == "proven_fix"
