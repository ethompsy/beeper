"""Tests for one-click investigation feedback (Story 3-4)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import respx
from flask.testing import FlaskClient


class TestSubmitFeedbackRoute:
    """Tests for POST /investigations/<id>/feedback route."""

    @respx.mock
    def test_feedback_accurate_returns_200(self, client: FlaskClient) -> None:
        """Test submitting 'accurate' feedback returns 200 with highlighted partial."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
            )
            assert response.status_code == 200
            assert b"feedback-btn-selected" in response.data
            assert b"Accurate" in response.data
            assert b"Feedback recorded" in response.data
            mock_svc.save_resolution_feedback.assert_called_once()
            call_args = mock_svc.save_resolution_feedback.call_args
            assert call_args[0][0] == "inv-feedback-001"
            assert call_args[0][1]["investigation_feedback"] == "accurate"
            mock_svc.close.assert_called_once()

    @respx.mock
    def test_feedback_inaccurate_returns_200(self, client: FlaskClient) -> None:
        """Test submitting 'inaccurate' feedback returns 200 with highlighted partial."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "inaccurate"},
            )
            assert response.status_code == 200
            assert b"feedback-btn-selected" in response.data
            assert b"Inaccurate" in response.data
            assert b"Feedback recorded" in response.data
            call_args = mock_svc.save_resolution_feedback.call_args
            assert call_args[0][1]["investigation_feedback"] == "inaccurate"

    @respx.mock
    def test_feedback_not_an_issue_returns_200(self, client: FlaskClient) -> None:
        """Test submitting 'not_an_issue' feedback returns 200 with highlighted partial."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "not_an_issue"},
            )
            assert response.status_code == 200
            assert b"feedback-btn-selected" in response.data
            assert b"Not an Issue" in response.data
            assert b"Feedback recorded" in response.data
            call_args = mock_svc.save_resolution_feedback.call_args
            assert call_args[0][1]["investigation_feedback"] == "not_an_issue"

    @respx.mock
    def test_feedback_invalid_type_returns_400(self, client: FlaskClient) -> None:
        """Test submitting invalid feedback type returns 400 error."""
        response = client.post(
            "/investigations/inv-feedback-001/feedback",
            data={"feedback_type": "maybe"},
        )
        assert response.status_code == 400
        assert b"Invalid feedback type" in response.data

    @respx.mock
    def test_feedback_empty_type_returns_400(self, client: FlaskClient) -> None:
        """Test submitting empty feedback type returns 400 error."""
        response = client.post(
            "/investigations/inv-feedback-001/feedback",
            data={"feedback_type": ""},
        )
        assert response.status_code == 400
        assert b"Invalid feedback type" in response.data

    @respx.mock
    def test_feedback_missing_type_returns_400(self, client: FlaskClient) -> None:
        """Test submitting no feedback_type field returns 400 error."""
        response = client.post(
            "/investigations/inv-feedback-001/feedback",
            data={},
        )
        assert response.status_code == 400
        assert b"Invalid feedback type" in response.data

    @respx.mock
    def test_feedback_boolean_type_returns_400(self, client: FlaskClient) -> None:
        """Test submitting boolean-like feedback type returns 400 error."""
        response = client.post(
            "/investigations/inv-feedback-001/feedback",
            data={"feedback_type": "true"},
        )
        assert response.status_code == 400
        assert b"Invalid feedback type" in response.data


    @respx.mock
    def test_feedback_saves_gracefully_for_nonexistent_investigation(
        self, client: FlaskClient
    ) -> None:
        """Test feedback saves gracefully even if investigation doesn't exist in Qdrant.

        The save_resolution_feedback method logs a warning but doesn't raise.
        """
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc
            # save_resolution_feedback doesn't raise for missing records

            response = client.post(
                "/investigations/inv-nonexistent/feedback",
                data={"feedback_type": "accurate"},
            )
            assert response.status_code == 200
            assert b"Feedback recorded" in response.data
            mock_svc.save_resolution_feedback.assert_called_once()

    @respx.mock
    def test_feedback_accessible_by_user_role(self, client: FlaskClient) -> None:
        """Test feedback endpoint is accessible by user role (not admin-only)."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
                headers={"X-Beeper-Role": "user"},
            )
            assert response.status_code == 200
            assert b"Feedback recorded" in response.data

    @respx.mock
    def test_feedback_records_user_header(self, client: FlaskClient) -> None:
        """Test feedback records X-Beeper-User header value."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
                headers={"X-Beeper-User": "sre@company.com"},
            )
            assert response.status_code == 200
            call_args = mock_svc.save_resolution_feedback.call_args
            assert call_args[0][1]["investigation_feedback_by"] == "sre@company.com"

    @respx.mock
    def test_feedback_records_default_user_when_no_header(
        self, client: FlaskClient
    ) -> None:
        """Test feedback records 'anonymous' when X-Beeper-User header is missing."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
            )
            assert response.status_code == 200
            call_args = mock_svc.save_resolution_feedback.call_args
            assert call_args[0][1]["investigation_feedback_by"] == "anonymous"

    @respx.mock
    def test_feedback_records_timestamp(self, client: FlaskClient) -> None:
        """Test feedback records ISO 8601 timestamp."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
            )
            assert response.status_code == 200
            call_args = mock_svc.save_resolution_feedback.call_args
            feedback_at = call_args[0][1]["investigation_feedback_at"]
            # Validate proper ISO 8601 format by parsing
            parsed = datetime.fromisoformat(feedback_at)
            assert parsed.tzinfo is not None  # timezone-aware

    @respx.mock
    def test_feedback_qdrant_failure_returns_503(self, client: FlaskClient) -> None:
        """Test feedback returns 503 when Qdrant/service is unavailable."""
        from beeper_ui.services.investigation_service import InvestigationServiceError

        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc
            mock_svc.save_resolution_feedback.side_effect = InvestigationServiceError(
                "Connection refused"
            )

            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
            )
            assert response.status_code == 503
            assert b"Unable to save feedback" in response.data
            mock_svc.close.assert_called_once()

    @respx.mock
    def test_feedback_change_overwrites_previous(
        self, client: FlaskClient
    ) -> None:
        """Test changing feedback overwrites previous (last feedback wins)."""
        with patch(
            "beeper_ui.routes.investigations.InvestigationService"
        ) as MockService:
            mock_svc = MagicMock()
            MockService.return_value = mock_svc

            # Submit "accurate" first
            client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "accurate"},
            )
            first_call = mock_svc.save_resolution_feedback.call_args
            assert first_call[0][1]["investigation_feedback"] == "accurate"

            # Change to "inaccurate"
            response = client.post(
                "/investigations/inv-feedback-001/feedback",
                data={"feedback_type": "inaccurate"},
            )
            assert response.status_code == 200
            assert b"Inaccurate" in response.data
            second_call = mock_svc.save_resolution_feedback.call_args
            assert second_call[0][1]["investigation_feedback"] == "inaccurate"
            assert mock_svc.save_resolution_feedback.call_count == 2


