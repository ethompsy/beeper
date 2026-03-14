"""Tests for LLM escalation events and retryable exit codes."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.agent import InvestigatorAgent, LlmUnavailableError, SourceClients
from beeper_investigator.llm.client import LlmClientError


class TestLlmUnavailableError:
    """Tests for LlmUnavailableError exception."""

    def test_is_runtime_error(self) -> None:
        err = LlmUnavailableError("test")
        assert isinstance(err, RuntimeError)

    def test_message(self) -> None:
        err = LlmUnavailableError("LLM connection failed")
        assert str(err) == "LLM connection failed"


class TestAgentLlmUnavailability:
    """Tests for agent handling of LLM unavailability."""

    def _make_agent(
        self,
    ) -> tuple[InvestigatorAgent, MagicMock, MagicMock]:
        """Build agent with mocked dependencies.

        Returns:
            (agent, mock_llm, mock_status_updater)
        """
        context = MagicMock()
        context.investigation_id = "test-inv-001"
        context.service = "test-service"
        context.condition = "high error rate"
        context.severity = "medium"
        kb_client = MagicMock()
        kb_client.health_check.return_value = True
        llm_client = MagicMock()
        sources = SourceClients()
        status_updater = MagicMock()
        agent = InvestigatorAgent(
            context=context,
            kb_client=kb_client,
            llm_client=llm_client,
            sources=sources,
            status_updater=status_updater,
        )
        return agent, llm_client, status_updater

    def test_llm_unavailable_sets_status(self) -> None:
        agent, mock_llm, mock_status = self._make_agent()
        mock_llm.test_connection.side_effect = LlmClientError("Connection refused")
        with pytest.raises(LlmUnavailableError):
            agent._initialize()
        mock_status.set_llm_unavailable.assert_called_once()
        call_arg = mock_status.set_llm_unavailable.call_args[0][0]
        assert "Connection refused" in call_arg

    def test_llm_unavailable_raises_correct_type(self) -> None:
        agent, mock_llm, _ = self._make_agent()
        mock_llm.test_connection.side_effect = LlmClientError("timeout")
        with pytest.raises(LlmUnavailableError) as exc_info:
            agent._initialize()
        assert "timeout" in str(exc_info.value)

    def test_llm_test_returns_false_triggers_unavailable(self) -> None:
        agent, mock_llm, mock_status = self._make_agent()
        mock_llm.test_connection.return_value = False
        with pytest.raises(LlmUnavailableError):
            agent._initialize()
        mock_status.set_llm_unavailable.assert_called_once()

    def test_agent_run_propagates_llm_unavailable(self) -> None:
        agent, mock_llm, _ = self._make_agent()
        mock_llm.test_connection.side_effect = LlmClientError("down")
        with pytest.raises(LlmUnavailableError):
            agent.run()


class TestEscalationEvent:
    """Tests for structured escalation log event in main.py."""

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    @patch("beeper_investigator.main.InvestigationContext")
    def test_llm_escalation_event_emitted(
        self,
        mock_ctx_cls: MagicMock,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_ctx = MagicMock()
        mock_ctx.investigation_id = "inv-escalation-test"
        mock_ctx.namespace = "default"
        mock_ctx_cls.from_env.return_value = mock_ctx

        mock_llm = MagicMock()
        mock_llm.provider = "anthropic"
        mock_llm.model = "claude-sonnet-4"
        mock_llm_cls.from_env.return_value = mock_llm

        mock_kb = MagicMock()
        mock_kb.health_check.return_value = True
        mock_kb_cls.return_value = mock_kb

        mock_status = MagicMock()
        mock_status_cls.return_value = mock_status

        # Make test_connection raise to trigger LlmUnavailableError
        mock_llm.test_connection.side_effect = LlmClientError("provider unreachable")

        from beeper_investigator.main import main

        with pytest.raises(SystemExit) as exc_info:
            with caplog.at_level(logging.ERROR, logger="beeper_investigator"):
                main()

        # Exit code 2 = retryable
        assert exc_info.value.code == 2

        # Verify escalation event fields are present in log records
        escalation_records = [
            r for r in caplog.records
            if getattr(r, "event", None) == "llm_escalation"
        ]
        assert len(escalation_records) == 1, "Expected exactly one llm_escalation event"
        record = escalation_records[0]
        assert getattr(record, "escalation_type") == "human_required"
        assert "provider unreachable" in getattr(record, "error_detail")

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    @patch("beeper_investigator.main.InvestigationContext")
    def test_retryable_exit_code(
        self,
        mock_ctx_cls: MagicMock,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
    ) -> None:
        mock_ctx = MagicMock()
        mock_ctx.investigation_id = "inv-retry-test"
        mock_ctx.namespace = "default"
        mock_ctx_cls.from_env.return_value = mock_ctx

        mock_llm = MagicMock()
        mock_llm.provider = "anthropic"
        mock_llm.model = "claude-sonnet-4"
        mock_llm_cls.from_env.return_value = mock_llm

        mock_kb = MagicMock()
        mock_kb.health_check.return_value = True
        mock_kb_cls.return_value = mock_kb

        mock_status = MagicMock()
        mock_status_cls.return_value = mock_status

        mock_llm.test_connection.side_effect = LlmClientError("timeout")

        from beeper_investigator.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 2

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    @patch("beeper_investigator.main.InvestigationContext")
    def test_non_retryable_exit_code(
        self,
        mock_ctx_cls: MagicMock,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
    ) -> None:
        mock_ctx = MagicMock()
        mock_ctx.investigation_id = "inv-noretry-test"
        mock_ctx.namespace = "default"
        mock_ctx_cls.from_env.return_value = mock_ctx

        # Raise LlmClientError (non-retryable) during initialization
        mock_llm_cls.from_env.side_effect = LlmClientError("Invalid API key")

        from beeper_investigator.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        # Exit code 1 = permanent failure
        assert exc_info.value.code == 1
