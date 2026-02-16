"""Tests for Knowledge Base routes."""

from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.routes.knowledge import (
    MAX_QUERY_LENGTH,
    VALID_ENTRY_TYPES,
    sanitize_query,
    validate_entry_type,
)
from beeper_ui.services.embedding_service import EmbeddingService
from beeper_ui.services.kb_service import KBEntry, KBServiceError
from beeper_ui.services.import_service import ImportResult


class TestSanitizeQuery:
    """Tests for sanitize_query function."""

    def test_strips_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        assert sanitize_query("  hello  ") == "hello"

    def test_removes_html_tags(self) -> None:
        """Test that HTML tags are removed."""
        assert sanitize_query("<script>alert(1)</script>search") == "alert(1)search"
        assert sanitize_query("test<b>bold</b>") == "testbold"

    def test_limits_length(self) -> None:
        """Test that query is truncated at max length."""
        long_query = "a" * 1000
        result = sanitize_query(long_query)
        assert len(result) == MAX_QUERY_LENGTH

    def test_empty_string(self) -> None:
        """Test empty string returns empty."""
        assert sanitize_query("") == ""
        assert sanitize_query("   ") == ""

    def test_none_handling(self) -> None:
        """Test None returns empty string."""
        assert sanitize_query(None) == ""  # type: ignore

    def test_normal_query_unchanged(self) -> None:
        """Test that normal queries are not modified."""
        query = "database connection timeout"
        assert sanitize_query(query) == query

    def test_removes_nested_tags(self) -> None:
        """Test that nested tags are removed."""
        assert sanitize_query("<div><script>x</script></div>") == "x"


class TestValidateEntryType:
    """Tests for validate_entry_type function."""

    def test_valid_investigation(self) -> None:
        """Test that 'investigation' is valid."""
        assert validate_entry_type("investigation") == "investigation"

    def test_valid_runbook(self) -> None:
        """Test that 'runbook' is valid."""
        assert validate_entry_type("runbook") == "runbook"

    def test_valid_correction(self) -> None:
        """Test that 'correction' is valid."""
        assert validate_entry_type("correction") == "correction"

    def test_invalid_type_returns_none(self) -> None:
        """Test that invalid entry types return None."""
        assert validate_entry_type("invalid") is None
        assert validate_entry_type("<script>alert(1)</script>") is None
        assert validate_entry_type("INVESTIGATION") is None  # Case-sensitive

    def test_empty_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert validate_entry_type("") is None

    def test_none_returns_none(self) -> None:
        """Test that None returns None."""
        assert validate_entry_type(None) is None

    def test_valid_types_constant(self) -> None:
        """Test that VALID_ENTRY_TYPES contains expected values."""
        assert "investigation" in VALID_ENTRY_TYPES
        assert "runbook" in VALID_ENTRY_TYPES
        assert "correction" in VALID_ENTRY_TYPES
        assert len(VALID_ENTRY_TYPES) == 3


def _make_entry(
    entry_id: str = "kb-123",
    entry_type: str = "investigation",
    title: str = "Test Entry",
    content: str = "Test content",
    service: str = "api",
) -> KBEntry:
    """Create a mock KBEntry for testing."""
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type=entry_type,
        title=title,
        content=content,
        service=service,
        created_at=None,
        updated_at=None,
        author="beeper",
        version=1,
        tags=["test"],
    )


class TestKBIndexRoute:
    """Tests for KB index route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_with_entries(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB index page renders with entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [
            _make_entry("kb-1", "investigation", "First Entry"),
            _make_entry("kb-2", "runbook", "Second Entry"),
        ]
        mock_service.get_available_services.return_value = ["api", "payments"]
        mock_service.get_entry_types.return_value = ["investigation", "runbook"]

        response = client.get("/knowledge/")
        assert response.status_code == 200
        assert b"First Entry" in response.data
        assert b"Second Entry" in response.data
        assert b"Knowledge Base" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_empty(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB index page with no entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["investigation", "runbook"]

        response = client.get("/knowledge/")
        assert response.status_code == 200
        assert b"No KB entries found" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_with_error(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB index page handles service errors."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.side_effect = KBServiceError(
            "Connection refused"
        )

        response = client.get("/knowledge/")
        assert response.status_code == 200
        assert b"Unable to fetch KB entries" in response.data
        assert b"Connection refused" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_with_service_filter(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB index with service filter."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_entry_types.return_value = []

        response = client.get("/knowledge/?service=api")
        assert response.status_code == 200
        mock_service.list_recent_entries.assert_called_with(
            limit=20, entry_type=None, service="api", date_from=None, date_to=None
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_htmx_partial(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test HTMX request returns partial content."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [
            _make_entry("kb-1", "investigation", "HTMX Entry")
        ]

        response = client.get("/knowledge/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Partial should not include full HTML structure
        assert b"<!DOCTYPE html>" not in response.data
        assert b"HTMX Entry" in response.data


class TestKBEntryRoute:
    """Tests for KB entry detail route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_entry_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB entry page renders with entry."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-test", "investigation", "Test Investigation", "## Summary\n\nDetails"
        )
        mock_service.list_related_entries.return_value = []

        response = client.get("/knowledge/kb-test")
        assert response.status_code == 200
        assert b"Test Investigation" in response.data
        assert b"investigation" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_entry_not_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB entry page returns 404 for missing entry."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = None

        response = client.get("/knowledge/non-existent")
        assert response.status_code == 404
        assert b"not found" in response.data.lower()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_entry_with_related(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB entry page shows related entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry("kb-main", service="api")
        mock_service.list_related_entries.return_value = [
            _make_entry("kb-related", "runbook", "Related Runbook", service="api")
        ]

        response = client.get("/knowledge/kb-main")
        assert response.status_code == 200
        # Related entries are loaded via HTMX, so check the endpoint exists
        mock_service.list_related_entries.assert_called_once()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_entry_with_error(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB entry page handles service errors."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.side_effect = KBServiceError("Database error")

        response = client.get("/knowledge/kb-error")
        assert response.status_code == 200
        assert b"Database error" in response.data


class TestKBRelatedRoute:
    """Tests for KB related entries route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_related_entries(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test related entries partial."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_related_entries.return_value = [
            _make_entry("kb-rel-1", "investigation", "Related 1"),
            _make_entry("kb-rel-2", "runbook", "Related 2"),
        ]

        response = client.get("/knowledge/kb-main/related?service=api")
        assert response.status_code == 200
        assert b"Related 1" in response.data
        assert b"Related 2" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_related_empty(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test related entries when none exist."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_related_entries.return_value = []

        response = client.get("/knowledge/kb-only/related")
        assert response.status_code == 200
        # Should not show related section when empty
        assert b"Related Entries" not in response.data


class TestKBSearchRoute:
    """Tests for KB semantic search route."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_with_results(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search returns results."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        entry1 = _make_entry("kb-1", "investigation", "Database Timeout")
        entry1.relevance_score = 0.85
        entry2 = _make_entry("kb-2", "runbook", "Connection Guide")
        entry2.relevance_score = 0.72

        mock_kb_service.search_semantic.return_value = ([entry1, entry2], True)

        response = client.get("/knowledge/search?q=database")
        assert response.status_code == 200
        assert b"Database Timeout" in response.data
        assert b"Connection Guide" in response.data
        assert b"85%" in response.data
        assert b"72%" in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_no_results(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search with no results."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        mock_kb_service.search_semantic.return_value = ([], True)

        response = client.get("/knowledge/search?q=nonexistent")
        assert response.status_code == 200
        assert b"No results found" in response.data
        assert b"nonexistent" in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_no_exact_matches(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search shows notice when no exact matches."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        entry = _make_entry("kb-1", "investigation", "Related Topic")
        entry.relevance_score = 0.55
        mock_kb_service.search_semantic.return_value = ([entry], False)

        response = client.get("/knowledge/search?q=obscure")
        assert response.status_code == 200
        assert b"No exact matches found" in response.data
        assert b"Related Topic" in response.data

    def test_kb_search_empty_query(self, client: FlaskClient) -> None:
        """Test search with empty query returns empty results."""
        response = client.get("/knowledge/search?q=")
        assert response.status_code == 200
        # Should not contain results or error
        assert b"No results found" not in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_with_filters(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search with type and service filters."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        mock_kb_service.search_semantic.return_value = ([], True)

        response = client.get(
            "/knowledge/search?q=test&entry_type=runbook&service=payments"
        )
        assert response.status_code == 200

        mock_kb_service.search_semantic.assert_called_once_with(
            query="test",
            limit=10,
            entry_type="runbook",
            service="payments",
            date_from=None,
            date_to=None,
            embedding_service=mock_embedding_service,
        )

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_service_error(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search handles service errors."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        mock_kb_service.search_semantic.side_effect = KBServiceError("Search failed")

        response = client.get("/knowledge/search?q=test")
        assert response.status_code == 200
        assert b"Search failed" in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_not_configured(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search shows error when embedding service not configured."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = False
        mock_get_embedding_service.return_value = mock_embedding_service

        response = client.get("/knowledge/search?q=test")
        assert response.status_code == 200
        assert b"not configured" in response.data.lower()


class TestKBSearchWithDateRange:
    """Tests for KB search with date range filtering."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_with_date_range(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search with date range filter."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding_service

        entry = _make_entry("kb-1", "investigation", "Test Entry")
        entry.relevance_score = 0.85
        mock_kb_service.search_semantic.return_value = ([entry], True)

        response = client.get("/knowledge/search?q=test&date_range=30d")
        assert response.status_code == 200

        # Verify date range was passed to search_semantic
        call_args = mock_kb_service.search_semantic.call_args
        assert call_args.kwargs.get("date_from") is not None
        assert call_args.kwargs.get("date_to") is not None

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_filter_only_mode(
        self,
        mock_get_kb_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test search with filters but no query (filter-only mode)."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service

        entry = _make_entry("kb-1", "investigation", "Test Entry")
        mock_kb_service.list_recent_entries.return_value = [entry]

        response = client.get("/knowledge/search?entry_type=investigation&service=api")
        assert response.status_code == 200
        assert b"Test Entry" in response.data

        # Should use list_recent_entries, not search_semantic
        mock_kb_service.list_recent_entries.assert_called_once()
        mock_kb_service.search_semantic.assert_not_called()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_filter_only_with_date_range(
        self,
        mock_get_kb_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test filter-only search with date range."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.list_recent_entries.return_value = []

        response = client.get("/knowledge/search?date_range=7d")
        assert response.status_code == 200

        # Verify date range was passed to list_recent_entries
        call_args = mock_kb_service.list_recent_entries.call_args
        assert call_args.kwargs.get("date_from") is not None
        assert call_args.kwargs.get("date_to") is not None

    def test_kb_search_no_filters_no_query(
        self,
        client: FlaskClient,
    ) -> None:
        """Test search with no query and no filters returns empty."""
        response = client.get("/knowledge/search")
        assert response.status_code == 200
        # Should not contain any result content
        assert b"search-results-list" not in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_filter_only_no_results(
        self,
        mock_get_kb_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test filter-only search with no matching results."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.list_recent_entries.return_value = []

        response = client.get("/knowledge/search?entry_type=investigation")
        assert response.status_code == 200
        assert b"No entries match the selected filters" in response.data

    def test_kb_search_clear_all_filters(
        self,
        client: FlaskClient,
    ) -> None:
        """Test clearing all filters returns to empty state."""
        # When all filter params are empty strings, should return empty (no filters active)
        response = client.get("/knowledge/search?q=&entry_type=&service=&date_range=")
        assert response.status_code == 200
        # Should not contain result list (no query, no filters)
        assert b"search-results-list" not in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_search_invalid_entry_type_ignored(
        self,
        mock_get_kb_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test that invalid entry_type values are ignored (security)."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.list_recent_entries.return_value = []

        # Pass an invalid/malicious entry_type
        response = client.get("/knowledge/search?entry_type=<script>alert(1)</script>")
        assert response.status_code == 200

        # Should not have been called with the malicious value
        # Since entry_type is invalid, it becomes None, so no filter is active
        # and no query means empty response
        mock_kb_service.list_recent_entries.assert_not_called()
        mock_kb_service.search_semantic.assert_not_called()


class TestKBIndexWithDateRange:
    """Tests for KB index with date range filtering."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_with_date_range(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KB index with date range filter."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["investigation"]

        response = client.get("/knowledge/?date_range=30d")
        assert response.status_code == 200

        # Verify date range was passed to list_recent_entries
        call_args = mock_service.list_recent_entries.call_args
        assert call_args.kwargs.get("date_from") is not None
        assert call_args.kwargs.get("date_to") is not None


class TestKBImportRoute:
    """Tests for KB import routes."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_page_get(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test GET request to import page."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api", "payments"]

        response = client.get("/knowledge/import")
        assert response.status_code == 200
        assert b"Import Runbook" in response.data
        assert b"api" in response.data
        assert b"payments" in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_paste_success(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test successful paste import."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.check_duplicate.return_value = None
        mock_kb_service.create_entry.return_value = "kb-new-123"
        mock_kb_service.get_available_services.return_value = []

        mock_embedding = MagicMock()
        mock_get_embedding.return_value = mock_embedding
        mock_embedding.is_configured.return_value = True

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "Test Runbook",
                "content": "This is the runbook content with enough text.",
                "service": "api",
                "tags": "tag1, tag2",
            },
        )

        assert response.status_code == 200
        assert b"kb-new-123" in response.data or b"imported" in response.data.lower()
        mock_kb_service.create_entry.assert_called_once()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_paste_validation_error(
        self, mock_get_kb_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test paste import with validation errors."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.get_available_services.return_value = []

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "AB",  # Too short
                "content": "short",  # Too short
                "service": "",
                "tags": "",
            },
        )

        assert response.status_code == 200
        assert b"at least" in response.data.lower() or b"error" in response.data.lower()
        mock_kb_service.create_entry.assert_not_called()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_duplicate_detected(
        self, mock_get_kb_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test import when duplicate is detected."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.check_duplicate.return_value = _make_entry(
            "kb-existing", "runbook", "Existing Runbook"
        )
        mock_kb_service.get_available_services.return_value = []

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "Existing Runbook",
                "content": "This is some content that is long enough.",
                "service": "api",
                "tags": "",
            },
        )

        assert response.status_code == 200
        assert b"duplicate" in response.data.lower() or b"exists" in response.data.lower()

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_file_upload_success(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test successful file upload import."""
        import io

        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.check_duplicate.return_value = None
        mock_kb_service.create_entry.return_value = "kb-file-123"
        mock_kb_service.get_available_services.return_value = []

        mock_embedding = MagicMock()
        mock_get_embedding.return_value = mock_embedding
        mock_embedding.is_configured.return_value = True

        # Create a fake markdown file
        file_content = b"""# My Test Runbook

## Overview

This is a test runbook for the import feature.

## Steps

1. Do something
2. Do something else
"""
        data = {
            "import_mode": "file",
            "file": (io.BytesIO(file_content), "test-runbook.md"),
            "service": "payments",
            "tags": "database, guide",
        }

        response = client.post(
            "/knowledge/import",
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        mock_kb_service.create_entry.assert_called_once()
        call_args = mock_kb_service.create_entry.call_args
        assert call_args.kwargs.get("title") == "My Test Runbook"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_file_invalid_extension(
        self, mock_get_kb_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test file upload with invalid extension is rejected."""
        import io

        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.get_available_services.return_value = []

        data = {
            "import_mode": "file",
            "file": (io.BytesIO(b"content"), "script.exe"),
            "service": "",
            "tags": "",
        }

        response = client.post(
            "/knowledge/import",
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        assert b"not allowed" in response.data.lower() or b"invalid" in response.data.lower()
        mock_kb_service.create_entry.assert_not_called()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_no_file_selected(
        self, mock_get_kb_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test file upload with no file selected."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.get_available_services.return_value = []

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "file",
                "service": "",
                "tags": "",
            },
        )

        assert response.status_code == 200
        assert b"no file" in response.data.lower() or b"select" in response.data.lower()

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_with_duplicate_create_new(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test creating new entry when duplicate exists but user chooses create."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.check_duplicate.return_value = _make_entry(
            "kb-existing", "runbook", "Existing Title"
        )
        mock_kb_service.create_entry.return_value = "kb-new-456"
        mock_kb_service.get_available_services.return_value = []

        mock_embedding = MagicMock()
        mock_get_embedding.return_value = mock_embedding
        mock_embedding.is_configured.return_value = True

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "Existing Title",
                "content": "New content that is long enough for validation.",
                "service": "api",
                "tags": "",
                "duplicate_action": "create",  # User chose to create new
            },
        )

        assert response.status_code == 200
        mock_kb_service.create_entry.assert_called_once()

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_with_duplicate_update(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test updating existing entry when duplicate is found."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.update_entry.return_value = 2
        mock_kb_service.get_available_services.return_value = []

        mock_embedding = MagicMock()
        mock_get_embedding.return_value = mock_embedding
        mock_embedding.is_configured.return_value = True

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "Existing Title",
                "content": "Updated content that is long enough.",
                "service": "api",
                "tags": "",
                "duplicate_action": "update",
                "duplicate_entry_id": "kb-existing",  # Entry ID from hidden form field
            },
        )

        assert response.status_code == 200
        mock_kb_service.update_entry.assert_called_once()
        # Verify update was called with correct entry_id
        call_kwargs = mock_kb_service.update_entry.call_args.kwargs
        assert call_kwargs.get("entry_id") == "kb-existing"

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_import_update_not_configured(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Test update path shows error when embedding service not configured."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.get_available_services.return_value = []

        mock_embedding = MagicMock()
        mock_get_embedding.return_value = mock_embedding
        mock_embedding.is_configured.return_value = False  # Not configured

        response = client.post(
            "/knowledge/import",
            data={
                "import_mode": "paste",
                "title": "Existing Title",
                "content": "Updated content that is long enough.",
                "service": "api",
                "tags": "",
                "duplicate_action": "update",
                "duplicate_entry_id": "kb-existing",
            },
        )

        assert response.status_code == 200
        assert b"not configured" in response.data.lower()
        mock_kb_service.update_entry.assert_not_called()
