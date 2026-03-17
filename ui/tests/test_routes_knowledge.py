"""Tests for Knowledge Base entry detail bi-directional investigation links."""

from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.services.kb_service import KBEntry


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


class TestKBEntryDetailLinks:
    """Tests for bi-directional investigation links on KB entry detail page."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_passes_source_investigation(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Verify entry detail page passes source_investigation to template context."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-with-source", "investigation", "Entry With Source"
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = {
            "investigation_id": "inv-source-abc",
            "relationship": "source",
        }
        mock_service.get_contributing_investigations.return_value = []

        response = client.get("/knowledge/kb-with-source")
        assert response.status_code == 200
        assert b"inv-source-abc" in response.data
        mock_service.get_source_investigation.assert_called_once_with("kb-with-source")

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_passes_contributing_investigations(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Verify entry detail page passes contributing_investigations to template."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-with-contribs", "investigation", "Entry With Contributors"
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = [
            {"investigation_id": "inv-contrib-1", "relationship": "contributing"},
            {"investigation_id": "inv-contrib-2", "relationship": "contributing"},
        ]

        response = client.get("/knowledge/kb-with-contribs")
        assert response.status_code == 200
        assert b"inv-contrib-1" in response.data
        assert b"inv-contrib-2" in response.data
        mock_service.get_contributing_investigations.assert_called_once_with(
            "kb-with-contribs"
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_with_both_source_and_contribs(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Verify entry detail renders both source and contributing links."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-both-links", "investigation", "Both Links Entry"
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = {
            "investigation_id": "inv-source-main",
            "relationship": "source",
        }
        mock_service.get_contributing_investigations.return_value = [
            {"investigation_id": "inv-contrib-extra", "relationship": "contributing"},
        ]

        response = client.get("/knowledge/kb-both-links")
        assert response.status_code == 200
        # Both source and contributing links should appear
        assert b"inv-source-main" in response.data
        assert b"inv-contrib-extra" in response.data
        assert b"Investigation Links" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_no_investigation_links(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Verify entry detail without investigation links renders correctly."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-no-links", "runbook", "No Links Entry"
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        response = client.get("/knowledge/kb-no-links")
        assert response.status_code == 200
        assert b"No Links Entry" in response.data
        # Investigation Links section should not appear
        assert b"Investigation Links" not in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_calls_both_link_methods(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Verify that get_source_investigation and get_contributing_investigations are called."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry("kb-verify-calls")
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        client.get("/knowledge/kb-verify-calls")

        mock_service.get_source_investigation.assert_called_once_with("kb-verify-calls")
        mock_service.get_contributing_investigations.assert_called_once_with(
            "kb-verify-calls"
        )
