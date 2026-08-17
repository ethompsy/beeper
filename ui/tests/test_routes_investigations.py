"""Tests for investigation linked-KB endpoint."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.services.kb_service import KBEntry


def _make_kb_entry(
    entry_id: str = "kb-123",
    entry_type: str = "investigation",
    title: str = "Test KB Entry",
    content: str = "Test content",
    service: str = "api",
    validation_status: str | None = None,
) -> KBEntry:
    """Create a mock KBEntry for testing."""
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type=entry_type,
        title=title,
        content=content,
        service=service,
        created_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=None,
        author="beeper",
        version=1,
        tags=["test"],
        validation_status=validation_status,
    )


class TestLinkedKBEndpoint:
    """Tests for the /<investigation_id>/linked-kb endpoint."""

    @patch("beeper_ui.services.kb_service.KBService")
    def test_linked_kb_returns_entries(
        self, mock_kb_class: MagicMock, client: FlaskClient
    ) -> None:
        """Test GET /<investigation_id>/linked-kb returns rendered HTML with KB entry links."""
        mock_kb_svc = MagicMock()
        mock_kb_class.return_value = mock_kb_svc
        mock_kb_svc.get_linked_kb_entries.return_value = [
            _make_kb_entry("kb-linked-1", "investigation", "Linked KB Entry 1"),
            _make_kb_entry("kb-linked-2", "runbook", "Linked KB Entry 2", service="payments"),
        ]

        response = client.get("/investigations/inv-abc123/linked-kb")
        assert response.status_code == 200
        assert b"Linked KB Entry 1" in response.data
        assert b"Linked KB Entry 2" in response.data
        mock_kb_svc.get_linked_kb_entries.assert_called_once_with("inv-abc123")

    @patch("beeper_ui.services.kb_service.KBService")
    def test_linked_kb_empty_state(
        self, mock_kb_class: MagicMock, client: FlaskClient
    ) -> None:
        """Test empty state when no linked KB entries exist."""
        mock_kb_svc = MagicMock()
        mock_kb_class.return_value = mock_kb_svc
        mock_kb_svc.get_linked_kb_entries.return_value = []

        response = client.get("/investigations/inv-xyz789/linked-kb")
        assert response.status_code == 200
        assert b"No KB entries were created from this investigation" in response.data
        mock_kb_svc.get_linked_kb_entries.assert_called_once_with("inv-xyz789")

    @patch("beeper_ui.services.kb_service.KBService")
    def test_linked_kb_entry_details_in_response(
        self, mock_kb_class: MagicMock, client: FlaskClient
    ) -> None:
        """Test that linked KB entry details appear in rendered HTML."""
        mock_kb_svc = MagicMock()
        mock_kb_class.return_value = mock_kb_svc
        mock_kb_svc.get_linked_kb_entries.return_value = [
            _make_kb_entry(
                "kb-detail-check",
                "investigation",
                "Detail Check Entry",
                service="payments",
            ),
        ]

        response = client.get("/investigations/inv-detail-check/linked-kb")
        assert response.status_code == 200
        assert b"Detail Check Entry" in response.data
        assert b"investigation" in response.data
        assert b"payments" in response.data

    @patch("beeper_ui.services.kb_service.KBService")
    def test_linked_kb_shows_validation_status_badge(
        self, mock_kb_class: MagicMock, client: FlaskClient
    ) -> None:
        """Test that linked KB entries show validation status badge."""
        mock_kb_svc = MagicMock()
        mock_kb_class.return_value = mock_kb_svc
        mock_kb_svc.get_linked_kb_entries.return_value = [
            _make_kb_entry(
                "kb-proven",
                "investigation",
                "Proven Entry",
                validation_status="proven",
            ),
        ]

        response = client.get("/investigations/inv-validation/linked-kb")
        assert response.status_code == 200
        assert b"proven" in response.data
