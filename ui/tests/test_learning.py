"""Tests for Learning from Diffs (Story 5-3)."""

from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from beeper_ui.services.kb_service import (
    LEARNING_CATEGORIES,
    Correction,
    KBEntry,
    KBService,
    KBServiceError,
    LearningPattern,
)
from beeper_ui.services.learning_service import (
    LearningService,
    LearningServiceError,
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


def _make_learning_pattern_payload(
    pattern_id: str = "lrn-abc123def456",
    entry_id: str = "kb-test123",
    correction_id: str = "corr-abc123",
    service_name: str = "api-gateway",
    category: str = "missing_context",
    description: str = "Should have included deployment history",
    original_snippet: str = "The outage was caused by high traffic",
    corrected_snippet: str = (
        "The outage was caused by a deployment"
        " that changed the health check timeout"
    ),
) -> dict:
    """Create a mock learning pattern payload."""
    return {
        "pattern_id": pattern_id,
        "entry_id": entry_id,
        "correction_id": correction_id,
        "service_name": service_name,
        "category": category,
        "description": description,
        "original_snippet": original_snippet,
        "corrected_snippet": corrected_snippet,
        "created_at": "2026-03-07T12:00:00+00:00",
    }


# ── Data Model Tests ──


class TestLearningPattern:
    """Tests for LearningPattern dataclass."""

    def test_from_qdrant(self) -> None:
        payload = _make_learning_pattern_payload()
        pattern = LearningPattern.from_qdrant(payload)
        assert pattern.pattern_id == "lrn-abc123def456"
        assert pattern.entry_id == "kb-test123"
        assert pattern.correction_id == "corr-abc123"
        assert pattern.service_name == "api-gateway"
        assert pattern.category == "missing_context"
        assert pattern.description == "Should have included deployment history"
        assert "high traffic" in pattern.original_snippet
        assert "health check timeout" in pattern.corrected_snippet
        assert pattern.created_at == "2026-03-07T12:00:00+00:00"

    def test_from_qdrant_defaults(self) -> None:
        pattern = LearningPattern.from_qdrant({})
        assert pattern.pattern_id == ""
        assert pattern.service_name == "general"
        assert pattern.category == "other"
        assert pattern.description == ""

    def test_learning_categories_constant(self) -> None:
        assert "missing_context" in LEARNING_CATEGORIES
        assert "incorrect_correlation" in LEARNING_CATEGORIES
        assert "wrong_conclusion" in LEARNING_CATEGORIES
        assert "unnecessary_info" in LEARNING_CATEGORIES
        assert "other" in LEARNING_CATEGORIES
        assert len(LEARNING_CATEGORIES) == 5


# ── KBService Learning Pattern Method Tests ──


class TestKBServiceLearningPatterns:
    """Tests for KBService learning pattern methods."""

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_learning_pattern(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        svc = KBService()
        pattern = svc.create_learning_pattern(
            entry_id="kb-test123",
            correction_id="corr-abc123",
            service_name="api-gateway",
            category="missing_context",
            description="Should have included deployment history",
            original_snippet="caused by high traffic",
            corrected_snippet="caused by deployment change",
        )
        assert pattern.pattern_id.startswith("lrn-")
        assert pattern.entry_id == "kb-test123"
        assert pattern.correction_id == "corr-abc123"
        assert pattern.service_name == "api-gateway"
        assert pattern.category == "missing_context"
        assert pattern.description == "Should have included deployment history"
        mock_client.upsert.assert_called_once()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_learning_pattern_invalid_category(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        svc = KBService()
        pattern = svc.create_learning_pattern(
            entry_id="kb-test123",
            correction_id="corr-abc123",
            service_name="api-gateway",
            category="invalid_category",
            description="Test",
        )
        assert pattern.category == "other"

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_create_learning_pattern_qdrant_error(
        self, mock_client_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.upsert.side_effect = Exception("Connection refused")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to create learning pattern"):
            svc.create_learning_pattern(
                entry_id="kb-test123",
                correction_id="corr-abc123",
                service_name="api-gateway",
                category="missing_context",
                description="Test",
            )

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_patterns_no_filter(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_point = MagicMock()
        mock_point.payload = _make_learning_pattern_payload()
        mock_client.scroll.return_value = ([mock_point], None)

        svc = KBService()
        patterns = svc.get_learning_patterns()
        assert len(patterns) == 1
        assert patterns[0].category == "missing_context"
        mock_client.scroll.assert_called_once()
        # No filter when no args
        call_kwargs = mock_client.scroll.call_args
        assert call_kwargs.kwargs.get("scroll_filter") is None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_patterns_by_service(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        patterns = svc.get_learning_patterns(service_name="api-gateway")
        assert len(patterns) == 0
        call_kwargs = mock_client.scroll.call_args
        assert call_kwargs.kwargs.get("scroll_filter") is not None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_patterns_by_category(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        patterns = svc.get_learning_patterns(category="wrong_conclusion")
        assert len(patterns) == 0
        call_kwargs = mock_client.scroll.call_args
        assert call_kwargs.kwargs.get("scroll_filter") is not None

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_patterns_qdrant_error(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.side_effect = Exception("Timeout")

        svc = KBService()
        with pytest.raises(KBServiceError, match="Failed to get learning patterns"):
            svc.get_learning_patterns()

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_summary(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        payloads = [
            _make_learning_pattern_payload(
                pattern_id="lrn-1", category="missing_context", service_name="api-gateway"
            ),
            _make_learning_pattern_payload(
                pattern_id="lrn-2", category="missing_context", service_name="api-gateway"
            ),
            _make_learning_pattern_payload(
                pattern_id="lrn-3", category="wrong_conclusion", service_name="auth-service"
            ),
        ]
        mock_points = []
        for p in payloads:
            mp = MagicMock()
            mp.payload = p
            mock_points.append(mp)

        mock_client.scroll.return_value = (mock_points, None)

        svc = KBService()
        summary = svc.get_learning_summary()
        assert summary["total"] == 3
        assert summary["by_category"]["missing_context"] == 2
        assert summary["by_category"]["wrong_conclusion"] == 1
        assert summary["by_service"]["api-gateway"] == 2
        assert summary["by_service"]["auth-service"] == 1
        assert len(summary["patterns"]) == 3

    @patch("beeper_ui.services.kb_service.QdrantClient")
    def test_get_learning_summary_empty(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        svc = KBService()
        summary = svc.get_learning_summary()
        assert summary["total"] == 0
        assert summary["by_category"] == {}
        assert summary["by_service"] == {}
        assert summary["patterns"] == []


# ── LearningService Tests ──


class TestLearningService:
    """Tests for LearningService LLM integration."""

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_analyze_correction(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '[{"category": "missing_context", "description": "Missing deployment info", '
            '"original_snippet": "high traffic", "corrected_snippet": "deployment change"}]'
        )
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        patterns = svc.analyze_correction(
            entry_content="The outage was caused by high traffic",
            revised_content="The outage was caused by a deployment change",
            entry_title="API Outage",
            service_name="api-gateway",
            correction_messages=[
                {"role": "user", "content": "The root cause was a deployment"},
                {"role": "assistant", "content": "Understood"},
            ],
        )

        assert len(patterns) == 1
        assert patterns[0]["category"] == "missing_context"
        assert patterns[0]["description"] == "Missing deployment info"
        mock_litellm.completion.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_analyze_correction_json_with_fences(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '```json\n[{"category": "wrong_conclusion", "description": "Wrong root cause"}]\n```'
        )
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        patterns = svc.analyze_correction(
            entry_content="old", revised_content="new",
            entry_title="T", service_name="s",
            correction_messages=[],
        )
        assert len(patterns) == 1
        assert patterns[0]["category"] == "wrong_conclusion"

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_analyze_correction_non_json_fallback(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Just a plain text response about corrections"
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        patterns = svc.analyze_correction(
            entry_content="old", revised_content="new",
            entry_title="T", service_name="s",
            correction_messages=[],
        )
        assert len(patterns) == 1
        assert patterns[0]["category"] == "other"
        assert "plain text" in patterns[0]["description"]

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_analyze_correction_llm_error(self, mock_litellm: MagicMock) -> None:
        mock_litellm.completion.side_effect = Exception("API error")

        svc = LearningService()
        with pytest.raises(LearningServiceError, match="LLM request failed"):
            svc.analyze_correction(
                entry_content="old", revised_content="new",
                entry_title="T", service_name="s",
                correction_messages=[],
            )

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_generate_prompt_adjustments(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"adjustments": ["Always check deployment logs within 1 hour", '
            '"Include health check timeout in root cause analysis"]}'
        )
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        adjustments = svc.generate_prompt_adjustments(
            patterns=[
                {"category": "missing_context", "description": "Missing deployment info"},
                {"category": "missing_context", "description": "Missing health check data"},
            ],
            service_name="api-gateway",
        )
        assert len(adjustments) == 2
        assert "deployment logs" in adjustments[0]

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    def test_generate_prompt_adjustments_empty_patterns(self) -> None:
        svc = LearningService()
        adjustments = svc.generate_prompt_adjustments(patterns=[])
        assert adjustments == []

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_generate_prompt_adjustments_llm_error(self, mock_litellm: MagicMock) -> None:
        mock_litellm.completion.side_effect = Exception("API error")

        svc = LearningService()
        with pytest.raises(LearningServiceError, match="LLM request failed"):
            svc.generate_prompt_adjustments(
                patterns=[{"category": "other", "description": "test"}],
            )

    def test_init_missing_env_vars(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LearningServiceError, match="environment variables are required"):
                LearningService()

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_analyze_correction_multiple_patterns(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '[{"category": "missing_context", "description": "Missing deployment info", '
            '"original_snippet": "a", "corrected_snippet": "b"}, '
            '{"category": "unnecessary_info", "description": "Removed noise", '
            '"original_snippet": "c", "corrected_snippet": "d"}]'
        )
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        patterns = svc.analyze_correction(
            entry_content="old", revised_content="new",
            entry_title="T", service_name="s",
            correction_messages=[],
        )
        assert len(patterns) == 2
        assert patterns[0]["category"] == "missing_context"
        assert patterns[1]["category"] == "unnecessary_info"


# ── Apply Revision Learning Hook Tests ──

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
                "content": "Fix this",
                "timestamp": "2026-03-07T10:00:00+00:00",
            },
            {
                "role": "assistant",
                "content": "Understood",
                "timestamp": "2026-03-07T10:00:01+00:00",
            },
        ]
    return {
        "correction_id": correction_id,
        "entry_id": entry_id,
        "messages": messages,
        "status": status,
        "summary": "Fix root cause",
        "created_at": "2026-03-07T10:00:00+00:00",
        "updated_at": "2026-03-07T10:00:01+00:00",
    }


class TestApplyRevisionLearningHook:
    """Tests for learning hook in kb_apply_revision route."""

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_apply_triggers_learning(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.return_value = [
            {"category": "missing_context", "description": "Missing info",
             "original_snippet": "a", "corrected_snippet": "b"},
        ]

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        assert response.status_code == 200
        mock_learn.analyze_correction.assert_called_once()
        mock_svc.create_learning_pattern.assert_called_once()

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_apply_learning_failure_nonblocking(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.side_effect = LearningServiceError("LLM down")

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        # Apply still succeeds even though learning failed
        assert response.status_code == 200
        assert b"Version" in response.data or response.status_code == 200

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_apply_stores_multiple_patterns(
        self,
        mock_get_kb: MagicMock,
        mock_get_embed: MagicMock,
        mock_get_learn: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        entry = _make_entry()
        mock_svc.get_entry.return_value = entry

        correction = Correction.from_qdrant(_make_correction_payload())
        mock_svc.get_correction.return_value = correction
        mock_svc.update_entry.return_value = 2
        mock_svc.update_correction.return_value = correction

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.analyze_correction.return_value = [
            {"category": "missing_context", "description": "A",
             "original_snippet": "a", "corrected_snippet": "b"},
            {"category": "wrong_conclusion", "description": "B",
             "original_snippet": "c", "corrected_snippet": "d"},
        ]

        response = client.post(
            "/knowledge/kb-test123/corrections/corr-abc123/apply",
            data={"revised_content": "New content"},
        )
        assert response.status_code == 200
        assert mock_svc.create_learning_pattern.call_count == 2


# ── Learning Insights Route Tests ──


class TestLearningRoutes:
    """Tests for learning insights routes."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_page(self, mock_get_kb: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_summary.return_value = {
            "total": 3,
            "by_category": {"missing_context": 2, "wrong_conclusion": 1},
            "by_service": {"api-gateway": 2, "auth-service": 1},
            "patterns": [
                LearningPattern.from_qdrant(_make_learning_pattern_payload()),
            ],
        }

        response = client.get("/knowledge/learning")
        assert response.status_code == 200
        assert b"Learning Insights" in response.data
        assert b"3 patterns learned" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_page_empty(self, mock_get_kb: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_summary.return_value = {
            "total": 0,
            "by_category": {},
            "by_service": {},
            "patterns": [],
        }

        response = client.get("/knowledge/learning")
        assert response.status_code == 200
        assert b"No learning patterns yet" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_page_error(self, mock_get_kb: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_summary.side_effect = KBServiceError("Qdrant down")

        response = client.get("/knowledge/learning")
        assert response.status_code == 200
        assert b"Unable to load learning data" in response.data

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_adjustments(
        self, mock_get_kb: MagicMock, mock_get_learn: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc

        patterns = [LearningPattern.from_qdrant(_make_learning_pattern_payload())]
        mock_svc.get_learning_patterns.return_value = patterns

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.generate_prompt_adjustments.return_value = [
            "Always check deployment logs",
            "Include health check data",
        ]

        response = client.get("/knowledge/learning/adjustments")
        assert response.status_code == 200
        assert b"deployment logs" in response.data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_adjustments_no_patterns(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.return_value = []

        response = client.get("/knowledge/learning/adjustments")
        assert response.status_code == 200
        assert b"No adjustments" in response.data or b"More correction patterns" in response.data

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_learning_adjustments_llm_error(
        self, mock_get_kb: MagicMock, mock_get_learn: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.return_value = [
            LearningPattern.from_qdrant(_make_learning_pattern_payload())
        ]

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.generate_prompt_adjustments.side_effect = LearningServiceError("LLM error")

        response = client.get("/knowledge/learning/adjustments")
        assert response.status_code == 503
        assert b"Unable to generate adjustments" in response.data


# ── Prompt Context API Tests ──


class TestPromptContextAPI:
    """Tests for prompt context API endpoint."""

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_prompt_context_with_patterns(
        self, mock_get_kb: MagicMock, mock_get_learn: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.return_value = [
            LearningPattern.from_qdrant(_make_learning_pattern_payload())
        ]

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.get_prompt_context.return_value = (
            "Based on past corrections: check deployment logs"
        )
        mock_learn.generate_prompt_adjustments.return_value = ["Check deployment logs"]

        response = client.get("/knowledge/api/learning/prompt-context/api-gateway")
        assert response.status_code == 200
        data = response.get_json()
        assert data["pattern_count"] == 1
        assert "deployment logs" in data["prompt_context"]
        assert len(data["adjustments"]) == 1

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_prompt_context_no_patterns(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.return_value = []

        response = client.get("/knowledge/api/learning/prompt-context/api-gateway")
        assert response.status_code == 200
        data = response.get_json()
        assert data["pattern_count"] == 0
        assert data["prompt_context"] == ""
        assert data["adjustments"] == []

    @patch("beeper_ui.routes.knowledge.get_learning_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_prompt_context_llm_error(
        self, mock_get_kb: MagicMock, mock_get_learn: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.return_value = [
            LearningPattern.from_qdrant(_make_learning_pattern_payload())
        ]

        mock_learn = MagicMock()
        mock_get_learn.return_value = mock_learn
        mock_learn.get_prompt_context.side_effect = LearningServiceError("LLM down")

        response = client.get("/knowledge/api/learning/prompt-context/api-gateway")
        assert response.status_code == 503
        data = response.get_json()
        assert "error" in data

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_prompt_context_qdrant_error(
        self, mock_get_kb: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_get_kb.return_value = mock_svc
        mock_svc.get_learning_patterns.side_effect = KBServiceError("Qdrant down")

        response = client.get("/knowledge/api/learning/prompt-context/api-gateway")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data


# ── LearningService.get_prompt_context Tests ──


class TestGetPromptContext:
    """Tests for LearningService.get_prompt_context method."""

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    @patch("beeper_ui.services.learning_service.litellm")
    def test_get_prompt_context_generates_text(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"adjustments": ["Check deployment logs", "Include health check data"]}'
        )
        mock_litellm.completion.return_value = mock_response

        svc = LearningService()
        context = svc.get_prompt_context(
            patterns=[
                {"category": "missing_context", "description": "Missing deployment info"},
            ],
            service_name="api-gateway",
        )
        assert "past corrections" in context
        assert "api-gateway" in context
        assert "Check deployment logs" in context

    @patch.dict(
        "os.environ",
        {
            "BEEPER_LLM_PROVIDER": "openai",
            "BEEPER_LLM_MODEL": "gpt-4",
            "BEEPER_LLM_API_KEY": "test",
        },
    )
    def test_get_prompt_context_empty_patterns(self) -> None:
        svc = LearningService()
        context = svc.get_prompt_context(patterns=[])
        assert context == ""
