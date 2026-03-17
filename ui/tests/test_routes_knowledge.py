"""Tests for Knowledge Base routes including entry detail links and service knowledge views."""

from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.routes.knowledge import _describe_edit_changes
from beeper_ui.services.kb_service import KBEntry, KBServiceError


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
        validation_status=None,
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
        mock_service.get_source_investigation.assert_called_once()
        call_args = mock_service.get_source_investigation.call_args
        assert call_args[0][0] == "kb-with-source"

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
        mock_service.get_contributing_investigations.assert_called_once()
        call_args = mock_service.get_contributing_investigations.call_args
        assert call_args[0][0] == "kb-with-contribs"

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

        mock_service.get_source_investigation.assert_called_once()
        assert mock_service.get_source_investigation.call_args[0][0] == "kb-verify-calls"
        mock_service.get_contributing_investigations.assert_called_once()
        assert mock_service.get_contributing_investigations.call_args[0][0] == "kb-verify-calls"


class TestServiceKnowledgeRoute:
    """Tests for the per-service knowledge view route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_returns_grouped_entries(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test GET /knowledge/services/<name>/knowledge returns grouped entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["payment-service"]
        mock_service.get_service_knowledge_grouped.return_value = {
            "root_causes": [_make_entry("kb-1", "investigation", "Root Cause Entry", service="payment-service")],
            "runbooks": [],
            "proven_fixes": [],
            "patterns": [],
        }
        mock_service.get_service_validation_counts.return_value = {
            "AI-generated": 1, "total": 1,
        }

        response = client.get("/knowledge/services/payment-service/knowledge")
        assert response.status_code == 200
        assert b"payment-service" in response.data
        assert b"Root Cause Entry" in response.data
        mock_service.get_service_knowledge_grouped.assert_called_once_with(
            service_name="payment-service",
            validation_status=None,
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_validation_filter(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test validation_status query param filters correctly."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_service_knowledge_grouped.return_value = {
            "root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": [],
        }
        mock_service.get_service_validation_counts.return_value = {"total": 0}

        response = client.get("/knowledge/services/api/knowledge?validation_status=proven")
        assert response.status_code == 200
        mock_service.get_service_knowledge_grouped.assert_called_once_with(
            service_name="api",
            validation_status="proven",
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_invalid_validation_filter_ignored(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test invalid validation_status is ignored."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_service_knowledge_grouped.return_value = {
            "root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": [],
        }
        mock_service.get_service_validation_counts.return_value = {"total": 0}

        response = client.get("/knowledge/services/api/knowledge?validation_status=invalid")
        assert response.status_code == 200
        mock_service.get_service_knowledge_grouped.assert_called_once_with(
            service_name="api",
            validation_status=None,
        )

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_empty_state(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test empty state shown when no entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["empty-svc"]
        mock_service.get_service_knowledge_grouped.return_value = {
            "root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": [],
        }
        mock_service.get_service_validation_counts.return_value = {"total": 0}

        response = client.get("/knowledge/services/empty-svc/knowledge")
        assert response.status_code == 200
        assert b"No knowledge entries yet" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_404_for_unknown_service(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test returns 404 for unknown service."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api", "payments"]

        response = client.get("/knowledge/services/nonexistent/knowledge")
        assert response.status_code == 404
        assert b"not found" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_renders_validation_badges(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test validation count badges are rendered."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_service_knowledge_grouped.return_value = {
            "root_causes": [_make_entry("kb-1", "investigation", "Entry 1", service="api")],
            "runbooks": [],
            "proven_fixes": [],
            "patterns": [],
        }
        mock_service.get_service_validation_counts.return_value = {
            "AI-generated": 3, "proven": 2, "total": 5,
        }

        response = client.get("/knowledge/services/api/knowledge")
        assert response.status_code == 200
        assert b"All (5)" in response.data
        assert b"proven (2)" in response.data
        assert b"AI-generated (3)" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_knowledge_handles_service_error(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test graceful handling of KBServiceError."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_service_knowledge_grouped.side_effect = KBServiceError("Qdrant down")

        response = client.get("/knowledge/services/api/knowledge")
        assert response.status_code == 200  # Degrades gracefully
        assert b"Failed to load knowledge entries" in response.data


class TestFilterPanelServiceLink:
    """Tests for the 'View Service Knowledge' link in the filter panel."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_filter_panel_shows_service_link_when_selected(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that selecting a service in KB index shows View Service Knowledge link."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = ["payment-service"]
        mock_service.get_entry_types.return_value = ["investigation"]

        response = client.get("/knowledge/?service=payment-service")
        assert response.status_code == 200
        assert b"View Service Knowledge" in response.data
        assert b"/knowledge/services/payment-service/knowledge" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_filter_panel_hides_service_link_when_no_service(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that no service link is shown when no service is selected."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_entry_types.return_value = ["investigation"]

        response = client.get("/knowledge/")
        assert response.status_code == 200
        assert b"View Service Knowledge" not in response.data


class TestConfirmEntryRoute:
    """Tests for POST /knowledge/<entry_id>/confirm route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_successful_confirm_redirects(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test successful confirmation redirects to entry detail page."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.confirm_entry.return_value = 2

        response = client.post(
            "/knowledge/kb-123/confirm",
            data={"user": "sre-sam"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/knowledge/kb-123" in response.headers["Location"]
        mock_service.confirm_entry.assert_called_once_with("kb-123", "sre-sam")

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_confirm_default_user(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test confirmation defaults to 'anonymous' when no user provided."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.confirm_entry.return_value = 2

        response = client.post(
            "/knowledge/kb-123/confirm",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        mock_service.confirm_entry.assert_called_once_with("kb-123", "anonymous")

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_confirm_error_flashes_message(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test KBServiceError flashes error and redirects."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.confirm_entry.side_effect = KBServiceError(
            "Can only confirm AI-generated entries, current status: proven"
        )

        response = client.post(
            "/knowledge/kb-123/confirm",
            data={"user": "sre-sam"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_confirm_button_visible_for_ai_generated(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that Confirm button appears for AI-generated entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-ai", "investigation", "AI Entry")
        entry.validation_status = "AI-generated"
        mock_service.get_entry.return_value = entry
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        response = client.get("/knowledge/kb-ai")
        assert response.status_code == 200
        assert b"Confirm as Accurate" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_confirm_button_hidden_for_proven(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that Confirm button is hidden for already-confirmed entries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-proven", "proven_fix", "Proven Entry")
        entry.validation_status = "proven"
        mock_service.get_entry.return_value = entry
        mock_service.list_related_entries.return_value = []
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        response = client.get("/knowledge/kb-proven")
        assert response.status_code == 200
        assert b"Confirm as Accurate" not in response.data


class TestEditRouteValidationStatus:
    """Tests for edit route setting validation_status='corrected' on content changes."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_content_change_sets_corrected(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that editing content sets validation_status to 'corrected'."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-edit-1", "investigation", "Original Title")
        entry.content = "Original content"
        entry.version = 1
        entry.validation_status = "AI-generated"
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.update_entry.return_value = 2

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-edit-1/edit",
            data={
                "title": "Original Title",
                "content": "Changed content",
                "tags": "",
                "version": "1",
            },
        )
        assert response.status_code == 200
        mock_service.update_entry.assert_called_once()
        call_kwargs = mock_service.update_entry.call_args
        assert call_kwargs.kwargs.get("validation_status") == "corrected"

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_tags_only_change_preserves_status(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that changing only tags does NOT set validation_status."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-edit-2", "investigation", "Same Title")
        entry.content = "Same content"
        entry.version = 1
        entry.validation_status = "AI-generated"
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.update_entry.return_value = 2

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-edit-2/edit",
            data={
                "title": "Same Title",
                "content": "Same content",
                "tags": "new-tag",
                "version": "1",
            },
        )
        assert response.status_code == 200
        mock_service.update_entry.assert_called_once()
        call_kwargs = mock_service.update_entry.call_args
        assert call_kwargs.kwargs.get("validation_status") is None

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_edit_handles_get_entry_failure(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that edit POST doesn't crash when get_entry fails (NameError fix)."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_available_services.return_value = []
        mock_service.get_entry.side_effect = KBServiceError("connection failed")
        mock_service.update_entry.return_value = 2

        # Should not crash with NameError — current_entry is None
        response = client.post(
            "/knowledge/kb-fail/edit",
            data={
                "title": "Title",
                "content": "Content",
                "tags": "",
                "version": "",
            },
        )
        # The edit should still proceed (validation_status=None since we can't compare)
        assert response.status_code == 200


class TestEditEntryType:
    """Tests for entry_type (category) editing in the edit route."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_get_edit_includes_entry_types(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that GET edit page includes entry_types in template context."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-types-1")
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = ["api"]
        mock_service.get_entry_types.return_value = ["correction", "investigation", "runbook"]

        response = client.get("/knowledge/kb-types-1/edit")
        assert response.status_code == 200
        # Template should render the category select with entry types
        assert b"entry_type" in response.data
        assert b"investigation" in response.data

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_post_edit_passes_entry_type(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that POST edit with entry_type passes it to update_entry()."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-types-2")
        entry.content = "Same content"
        entry.version = 1
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["correction", "investigation", "runbook"]
        mock_service.update_entry.return_value = 2

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-types-2/edit",
            data={
                "title": "Test Entry",
                "content": "Same content",
                "tags": "test",
                "version": "1",
                "entry_type": "runbook",
            },
        )
        assert response.status_code == 200
        mock_service.update_entry.assert_called_once()
        call_kwargs = mock_service.update_entry.call_args
        assert call_kwargs.kwargs.get("entry_type") == "runbook"


class TestEditCorrectionRecording:
    """Tests for recording corrections in the corrections collection on edit."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_content_change_creates_correction(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that editing content creates a correction record."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-corr-1", "investigation", "Original Title")
        entry.content = "Original content"
        entry.version = 1
        entry.validation_status = "AI-generated"
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["investigation"]
        mock_service.update_entry.return_value = 2

        mock_correction = MagicMock()
        mock_correction.correction_id = "corr-abc123"
        mock_service.create_correction.return_value = mock_correction

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-corr-1/edit",
            data={
                "title": "Original Title",
                "content": "Changed content here",
                "tags": "test",
                "version": "1",
            },
        )
        assert response.status_code == 200
        # Correction should be created and immediately applied
        mock_service.create_correction.assert_called_once()
        create_kwargs = mock_service.create_correction.call_args.kwargs
        assert "Manual edit" in create_kwargs["user_message"]
        mock_service.update_correction.assert_called_once_with(
            correction_id="corr-abc123",
            status="applied",
        )

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_tags_only_change_no_correction(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that changing only tags does NOT create a correction."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-corr-2", "investigation", "Same Title")
        entry.content = "Same content"
        entry.version = 1
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["investigation"]
        mock_service.update_entry.return_value = 2

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-corr-2/edit",
            data={
                "title": "Same Title",
                "content": "Same content",
                "tags": "new-tag",
                "version": "1",
            },
        )
        assert response.status_code == 200
        mock_service.create_correction.assert_not_called()


class TestHistoryRestoreButton:
    """Tests for restore button on version history page."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_history_has_restore_for_non_current(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Test that history page shows Restore button for non-current versions."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-hist-1")
        entry.version = 3
        mock_service.get_entry.return_value = entry
        mock_service.list_versions.return_value = [
            {
                "version": 2,
                "author": "edit",
                "updated_at": "2026-01-02T00:00:00Z",
                "title": "Old Title",
                "content_length": 100,
                "tags": ["test"],
                "service": "api",
            },
            {
                "version": 1,
                "author": "beeper",
                "updated_at": "2026-01-01T00:00:00Z",
                "title": "Initial Title",
                "content_length": 50,
                "tags": [],
                "service": "api",
            },
        ]

        response = client.get("/knowledge/kb-hist-1/history")
        assert response.status_code == 200
        # Non-current versions should have Restore button
        assert b"Restore" in response.data
        # The restore form should target the existing restore route
        assert b"/knowledge/kb-hist-1/restore/" in response.data


class TestDescribeEditChanges:
    """Tests for _describe_edit_changes() helper function."""

    def test_title_change(self) -> None:
        """Test description when only title changes."""
        entry = _make_entry("kb-desc-1", title="Old Title")
        result = _describe_edit_changes(entry, "New Title", "Test content", ["test"], None)
        assert "Title changed" in result

    def test_content_added(self) -> None:
        """Test description when content is expanded."""
        entry = _make_entry("kb-desc-2", content="Short")
        result = _describe_edit_changes(entry, "Test Entry", "Short with more text", ["test"], None)
        assert "chars added" in result

    def test_content_removed(self) -> None:
        """Test description when content is shortened."""
        entry = _make_entry("kb-desc-3", content="Long content here")
        result = _describe_edit_changes(entry, "Test Entry", "Short", ["test"], None)
        assert "chars removed" in result

    def test_tags_change(self) -> None:
        """Test description when tags change."""
        entry = _make_entry("kb-desc-4")
        result = _describe_edit_changes(entry, "Test Entry", "Test content", ["new-tag"], None)
        assert "Tags updated" in result

    def test_category_change(self) -> None:
        """Test description when entry_type changes."""
        entry = _make_entry("kb-desc-5", entry_type="investigation")
        result = _describe_edit_changes(entry, "Test Entry", "Test content", ["test"], "runbook")
        assert "Category changed to runbook" in result

    def test_fallback_when_no_detectable_changes(self) -> None:
        """Test fallback message when changes aren't detectable."""
        entry = _make_entry("kb-desc-6")
        result = _describe_edit_changes(entry, "Test Entry", "Test content", ["test"], None)
        assert result == "Content modified"


class TestEditEntryTypeValidation:
    """Tests for entry_type validation in POST handler."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_invalid_entry_type_rejected(
        self, mock_get_service: MagicMock, mock_get_embedding: MagicMock, client: FlaskClient
    ) -> None:
        """Test that invalid entry_type values are silently ignored."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        entry = _make_entry("kb-val-1")
        entry.content = "Same content"
        entry.version = 1
        mock_service.get_entry.return_value = entry
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = ["investigation"]
        mock_service.update_entry.return_value = 2

        mock_emb = MagicMock()
        mock_emb.is_configured.return_value = True
        mock_get_embedding.return_value = mock_emb

        response = client.post(
            "/knowledge/kb-val-1/edit",
            data={
                "title": "Test Entry",
                "content": "Same content",
                "tags": "test",
                "version": "1",
                "entry_type": "malicious_injection",
            },
        )
        assert response.status_code == 200
        call_kwargs = mock_service.update_entry.call_args
        # Invalid entry_type should be rejected (set to None)
        assert call_kwargs.kwargs.get("entry_type") is None
