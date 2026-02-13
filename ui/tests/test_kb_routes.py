"""Tests for Knowledge Base routes."""

from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.routes.knowledge import MAX_QUERY_LENGTH, sanitize_query
from beeper_ui.services.embedding_service import EmbeddingService
from beeper_ui.services.kb_service import KBEntry, KBServiceError


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
            limit=20, entry_type=None, service="api"
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
