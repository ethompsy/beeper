"""Tests for the Conversational Corrections Interface (Story 5-1)."""

from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from beeper_ui.services.kb_service import (
    Correction,
    CorrectionMessage,
    KBEntry,
    KBService,
    KBServiceError,
)


def _make_entry(
    entry_id: str = "kb-test123",
    title: str = "Test Entry",
    content: str = "Test content about a service outage",
    service: str = "api-gateway",
) -> KBEntry:
    """Create a mock KBEntry for testing."""
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type="investigation",
        title=title,
        content=content,
        service=service,
        created_at=None,
        updated_at=None,
        author="beeper",
        version=1,
        tags=["test"],
    )


def _make_correction_payload(
    correction_id: str = "corr-abc123",
    entry_id: str = "kb-test123",
    status: str = "pending",
    messages: list | None = None,
) -> dict:
    """Create a mock correction payload."""
    if messages is None:
        messages = [
            {
                "role": "user",
                "content": "The root cause was actually a DNS issue",
                "timestamp": "2026-03-07T10:00:00+00:00",
            },
            {
                "role": "assistant",
                "content": "I understand you want to change the root cause to a DNS issue.",
                "timestamp": "2026-03-07T10:00:01+00:00",
            },
        ]
    return {
        "correction_id": correction_id,
        "entry_id": entry_id,
        "messages": messages,
        "status": status,
        "summary": "Change root cause to DNS issue",
        "created_at": "2026-03-07T10:00:00+00:00",
        "updated_at": "2026-03-07T10:00:01+00:00",
    }


# ── Data Model Tests ──


class TestCorrectionMessage:
    """Tests for CorrectionMessage dataclass."""

    def test_creation(self) -> None:
        msg = CorrectionMessage(
            role="user",
            content="Fix the root cause",
            timestamp="2026-03-07T10:00:00+00:00",
        )
        assert msg.role == "user"
        assert msg.content == "Fix the root cause"
        assert msg.timestamp == "2026-03-07T10:00:00+00:00"


class TestCorrection:
    """Tests for Correction dataclass."""

    def test_from_qdrant_full(self) -> None:
        payload = _make_correction_payload()
        correction = Correction.from_qdrant(payload)
        assert correction.correction_id == "corr-abc123"
        assert correction.entry_id == "kb-test123"
        assert correction.status == "pending"
        assert correction.summary == "Change root cause to DNS issue"
        assert len(correction.messages) == 2
        assert correction.messages[0].role == "user"
        assert correction.messages[1].role == "assistant"

    def test_from_qdrant_empty(self) -> None:
        correction = Correction.from_qdrant({})
        assert correction.correction_id == ""
        assert correction.entry_id == ""
        assert correction.status == "pending"
        assert correction.summary is None
        assert correction.messages == []

    def test_from_qdrant_no_messages(self) -> None:
        payload = _make_correction_payload(messages=[])
        correction = Correction.from_qdrant(payload)
        assert correction.messages == []


# ── KBService Correction Method Tests ──


class TestKBServiceCorrections:
    """Tests for KBService correction methods."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_correction(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        svc = KBService()
        correction = svc.create_correction(
            entry_id="kb-test123",
            user_message="The root cause was DNS",
            assistant_response="I understand the correction.",
            summary="Change root cause",
        )

        assert correction.entry_id == "kb-test123"
        assert correction.status == "pending"
        assert correction.summary == "Change root cause"
        assert len(correction.messages) == 2
        assert correction.messages[0].role == "user"
        assert correction.messages[0].content == "The root cause was DNS"
        assert correction.messages[1].role == "assistant"
        assert correction.correction_id.startswith("corr-")
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_correction_qdrant_error(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.upsert.side_effect = Exception("connection failed")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to create correction"):
            svc.create_correction(
                entry_id="kb-test123",
                user_message="Fix this",
                assistant_response="OK",
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_corrections_for_entry(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point1 = MagicMock()
        point1.payload = _make_correction_payload(
            correction_id="corr-1",
            entry_id="kb-test123",
        )
        point2 = MagicMock()
        point2.payload = _make_correction_payload(
            correction_id="corr-2",
            entry_id="kb-test123",
        )
        # Make corr-2 newer
        point2.payload["created_at"] = "2026-03-08T10:00:00+00:00"

        mock_client.scroll.return_value = ([point1, point2], None)

        svc = KBService()
        corrections = svc.get_corrections_for_entry("kb-test123")

        assert len(corrections) == 2
        # Should be sorted descending by created_at
        assert corrections[0].correction_id == "corr-2"
        assert corrections[1].correction_id == "corr-1"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_corrections_for_entry_empty(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        corrections = svc.get_corrections_for_entry("kb-nonexist")
        assert corrections == []

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_correction(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.payload = _make_correction_payload()
        mock_client.scroll.return_value = ([point], None)

        svc = KBService()
        correction = svc.get_correction("corr-abc123")

        assert correction is not None
        assert correction.correction_id == "corr-abc123"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_correction_not_found(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        assert svc.get_correction("corr-nonexist") is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_add_correction_message(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-uuid"
        point.payload = _make_correction_payload()
        mock_client.scroll.return_value = ([point], None)

        svc = KBService()
        updated = svc.add_correction_message(
            correction_id="corr-abc123",
            role="user",
            content="Let me clarify - it was specifically a DNS TTL issue",
        )

        assert len(updated.messages) == 3
        assert updated.messages[2].role == "user"
        assert "DNS TTL" in updated.messages[2].content
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_add_correction_message_not_found(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        with pytest.raises(KBServiceError, match="Correction not found"):
            svc.add_correction_message(
                correction_id="corr-nonexist",
                role="user",
                content="test",
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_correction_status(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-uuid"
        point.payload = _make_correction_payload()
        mock_client.scroll.return_value = ([point], None)

        svc = KBService()
        updated = svc.update_correction(
            correction_id="corr-abc123",
            status="applied",
        )

        assert updated.status == "applied"
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_correction_summary(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        point = MagicMock()
        point.id = "point-uuid"
        point.payload = _make_correction_payload()
        mock_client.scroll.return_value = ([point], None)

        svc = KBService()
        updated = svc.update_correction(
            correction_id="corr-abc123",
            summary="Updated summary",
        )

        assert updated.summary == "Updated summary"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_update_correction_not_found(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        with pytest.raises(KBServiceError, match="Correction not found"):
            svc.update_correction(correction_id="corr-nonexist", status="applied")


# ── CorrectionService Tests ──


class TestCorrectionService:
    """Tests for the CorrectionService (LLM integration)."""

    @patch("beeper_ui.services.correction_service.litellm")
    def test_process_correction(self, mock_litellm: MagicMock) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"summary": "Change root cause to DNS", '
            '"understood_changes": ["Update root cause from load balancer to DNS issue"]}'
        )
        mock_litellm.completion.return_value = mock_response

        svc = CorrectionService.__new__(CorrectionService)
        svc._model = "claude-3-5-sonnet-20241022"

        result = svc.process_correction(
            entry_content="Root cause: load balancer failure",
            entry_title="API Outage 2026-03-01",
            correction_text="The root cause was actually a DNS issue",
        )

        assert result["summary"] == "Change root cause to DNS"
        assert len(result["understood_changes"]) == 1
        mock_litellm.completion.assert_called_once()

    @patch("beeper_ui.services.correction_service.litellm")
    def test_process_correction_invalid_json(self, mock_litellm: MagicMock) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I understand your correction about DNS."
        mock_litellm.completion.return_value = mock_response

        svc = CorrectionService.__new__(CorrectionService)
        svc._model = "claude-3-5-sonnet-20241022"

        result = svc.process_correction(
            entry_content="Root cause: load balancer",
            entry_title="Test",
            correction_text="Fix the root cause",
        )

        # Should fall back to plain text response
        assert "summary" in result
        assert isinstance(result["understood_changes"], list)

    @patch("beeper_ui.services.correction_service.litellm")
    def test_process_reply(self, mock_litellm: MagicMock) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"summary": "Updated: DNS TTL too high", '
            '"understood_changes": ["Specify DNS TTL was set to 24h instead of 60s"]}'
        )
        mock_litellm.completion.return_value = mock_response

        svc = CorrectionService.__new__(CorrectionService)
        svc._model = "claude-3-5-sonnet-20241022"

        conversation_history = [
            {"role": "user", "content": "Root cause was DNS"},
            {"role": "assistant", "content": "I understand - DNS issue."},
        ]

        result = svc.process_reply(
            entry_content="Root cause: load balancer",
            entry_title="Test",
            conversation_history=conversation_history,
            reply_text="Specifically, the DNS TTL was too high",
        )

        assert "summary" in result
        mock_litellm.completion.assert_called_once()

    @patch("beeper_ui.services.correction_service.litellm")
    def test_process_correction_llm_error(self, mock_litellm: MagicMock) -> None:
        from beeper_ui.services.correction_service import (
            CorrectionService,
            CorrectionServiceError,
        )

        mock_litellm.completion.side_effect = Exception("LLM unavailable")

        svc = CorrectionService.__new__(CorrectionService)
        svc._model = "claude-3-5-sonnet-20241022"

        with pytest.raises(CorrectionServiceError, match="LLM request failed"):
            svc.process_correction(
                entry_content="content",
                entry_title="title",
                correction_text="fix it",
            )

    def test_parse_response_valid_json(self) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        result = CorrectionService._parse_response(
            '{"summary": "test", "understood_changes": ["change1"]}'
        )
        assert result["summary"] == "test"
        assert result["understood_changes"] == ["change1"]

    def test_parse_response_code_fence_json(self) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        result = CorrectionService._parse_response(
            '```json\n{"summary": "test", "understood_changes": ["change1"]}\n```'
        )
        assert result["summary"] == "test"

    def test_parse_response_plain_text(self) -> None:
        from beeper_ui.services.correction_service import CorrectionService

        result = CorrectionService._parse_response("Just a plain text response")
        assert result["summary"] == "Just a plain text response"
        assert result["understood_changes"] == ["Just a plain text response"]


# ── Route Tests ──


class TestCorrectionRoutes:
    """Tests for correction-related routes."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_get_correction_panel(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = _make_entry()

        response = client.get(
            "/knowledge/kb-test123/corrections/panel",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assert b"correction" in response.data.lower()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_get_correction_panel_entry_not_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = None

        response = client.get("/knowledge/kb-nonexist/corrections/panel")
        assert response.status_code == 404

    @patch("beeper_ui.routes.knowledge.get_correction_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_submit_correction(
        self,
        mock_get_service: MagicMock,
        mock_get_corr_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        mock_corr_svc = MagicMock()
        mock_get_corr_service.return_value = mock_corr_svc
        mock_corr_svc.process_correction.return_value = {
            "summary": "Change root cause to DNS",
            "understood_changes": ["Update root cause"],
        }

        mock_correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.create_correction.return_value = mock_correction

        response = client.post(
            "/knowledge/kb-test123/corrections",
            data={"correction_text": "The root cause was DNS"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        mock_corr_svc.process_correction.assert_called_once()
        mock_svc.create_correction.assert_called_once()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_submit_correction_empty_text(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = _make_entry()

        response = client.post(
            "/knowledge/kb-test123/corrections",
            data={"correction_text": ""},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_submit_correction_entry_not_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = None

        response = client.post(
            "/knowledge/kb-nonexist/corrections",
            data={"correction_text": "Fix this"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 404

    @patch("beeper_ui.routes.knowledge.get_correction_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_submit_correction_reply(
        self,
        mock_get_service: MagicMock,
        mock_get_corr_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        mock_correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = mock_correction

        mock_corr_svc = MagicMock()
        mock_get_corr_service.return_value = mock_corr_svc
        mock_corr_svc.process_reply.return_value = {
            "summary": "Clarified: DNS TTL issue",
            "understood_changes": ["DNS TTL was too high"],
        }

        ts = "2026-03-07T10:00:00+00:00"
        reply_messages = [
            {"role": "user", "content": "DNS issue", "timestamp": ts},
            {"role": "assistant", "content": "Got it", "timestamp": ts},
            {"role": "user", "content": "TTL was too high", "timestamp": ts},
            {"role": "assistant", "content": "Clarified", "timestamp": ts},
        ]
        updated_correction = Correction.from_qdrant(
            _make_correction_payload(messages=reply_messages)
        )
        mock_svc.add_correction_message.return_value = updated_correction

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/reply",
            data={"reply_text": "TTL was too high"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_correction_reply_not_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = _make_entry()
        mock_svc.get_correction.return_value = None

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-nonexist/reply",
            data={"reply_text": "test"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 404

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_get_correction_history(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = _make_entry()

        corrections = [
            Correction.from_qdrant(
                _make_correction_payload(correction_id="corr-1")
            ),
            Correction.from_qdrant(
                _make_correction_payload(
                    correction_id="corr-2", status="applied"
                )
            ),
        ]
        mock_svc.get_corrections_for_entry.return_value = corrections

        response = client.get(
            "/knowledge/kb-test123/corrections",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_get_correction_history_entry_not_found(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = None

        response = client.get("/knowledge/kb-nonexist/corrections")
        assert response.status_code == 404

    @patch("beeper_ui.routes.knowledge.get_correction_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_submit_correction_llm_error(
        self,
        mock_get_service: MagicMock,
        mock_get_corr_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        from beeper_ui.services.correction_service import CorrectionServiceError

        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.get_entry.return_value = _make_entry()

        mock_corr_svc = MagicMock()
        mock_get_corr_service.return_value = mock_corr_svc
        mock_corr_svc.process_correction.side_effect = CorrectionServiceError("LLM unavailable")

        response = client.post(
            "/knowledge/kb-test123/corrections",
            data={"correction_text": "Fix this"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 503

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_no_regressions_kb_index(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """Ensure existing KB routes still work."""
        mock_svc = MagicMock()
        mock_get_service.return_value = mock_svc
        mock_svc.list_recent_entries.return_value = []
        mock_svc.get_available_services.return_value = []
        mock_svc.get_entry_types.return_value = []

        response = client.get("/knowledge/")
        assert response.status_code == 200
