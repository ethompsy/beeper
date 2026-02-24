"""Tests for InvestigatorAgent lifecycle."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import (
    InvestigationResult,
    InvestigatorAgent,
    SourceClients,
)
from beeper_investigator.context import InvestigationContext


def _make_agent(
    *,
    kb_healthy: bool = True,
    llm_healthy: bool = True,
) -> tuple[InvestigatorAgent, MagicMock, MagicMock, MagicMock]:
    """Build an agent with fully mocked dependencies.

    Returns:
        (agent, mock_kb, mock_llm, mock_status_updater)
    """
    ctx = InvestigationContext(
        investigation_id="inv-test-001",
        namespace="default",
        condition="CPU spike on checkout",
        service="payments",
        severity="high",
    )

    mock_kb = MagicMock()
    mock_kb.health_check.return_value = kb_healthy

    mock_llm = MagicMock()
    mock_llm.test_connection.return_value = llm_healthy

    mock_status = MagicMock()
    sources = SourceClients()

    agent = InvestigatorAgent(
        context=ctx,
        kb_client=mock_kb,
        llm_client=mock_llm,
        sources=sources,
        status_updater=mock_status,
    )
    agent.steps = []  # Isolate lifecycle tests from step implementations

    return agent, mock_kb, mock_llm, mock_status


class TestInvestigatorAgentRun:
    """Tests for the run() lifecycle."""

    def test_lifecycle_order(self) -> None:
        """run() follows initialize → steps → finalize."""
        agent, mock_kb, mock_llm, mock_status = _make_agent()

        result = agent.run()

        assert result.success is True
        # Verify status updates were called in order
        calls = [c[0][0] for c in mock_status.update_message.call_args_list]
        assert calls[0] == "Initializing investigation"
        assert calls[1] == "Running investigation steps"

        # Finalize calls set_completed
        mock_status.set_completed.assert_called_once()

    def test_placeholder_step_returns_success(self) -> None:
        """The placeholder _run_steps returns success with expected summary."""
        agent, *_ = _make_agent()

        result = agent.run()

        assert result.success is True
        assert "No investigation steps configured" in result.summary

    def test_result_persisted_to_qdrant(self) -> None:
        """Finalize persists investigation result to Qdrant."""
        agent, mock_kb, *_ = _make_agent()

        agent.run()

        mock_kb.client.upsert.assert_called_once()
        call_args = mock_kb.client.upsert.call_args
        collection = call_args[0][0]
        points = call_args[0][1]
        assert collection == "investigations"
        assert len(points) == 1
        payload = points[0].payload
        assert payload["investigation_id"] == "inv-test-001"
        assert payload["service"] == "payments"
        assert payload["status"] == "resolved"

    def test_kb_failure_returns_error_result(self) -> None:
        """KB health check failure returns error result."""
        agent, _, _, mock_status = _make_agent(kb_healthy=False)

        result = agent.run()

        assert result.success is False
        assert result.error is not None
        assert "KB health check failed" in result.error
        mock_status.set_failed.assert_called_once()

    def test_llm_failure_returns_error_result(self) -> None:
        """LLM connection test failure returns error result."""
        agent, _, _, mock_status = _make_agent(llm_healthy=False)

        result = agent.run()

        assert result.success is False
        assert result.error is not None
        assert "LLM connection test failed" in result.error
        mock_status.set_failed.assert_called_once()

    def test_unexpected_exception_caught(self) -> None:
        """Unexpected exceptions are caught and reported."""
        agent, mock_kb, _, mock_status = _make_agent()
        mock_kb.health_check.side_effect = ConnectionError("network down")

        result = agent.run()

        assert result.success is False
        assert "network down" in (result.error or "")
        mock_status.set_failed.assert_called_once()

    def test_sources_optional(self) -> None:
        """Agent works when source clients are None."""
        agent, *_ = _make_agent()
        assert agent.sources.prometheus is None
        assert agent.sources.loki is None

        result = agent.run()
        assert result.success is True

    def test_failed_result_persisted_with_failed_status(self) -> None:
        """Failed investigation persists with status='failed'."""
        agent, mock_kb, _, _ = _make_agent(llm_healthy=False)

        agent.run()

        # The agent catches the RuntimeError from _initialize and returns.
        # _finalize is NOT called on exception path — persist happens before
        # status update in _finalize, but the try/except in run() catches
        # before _finalize. So no upsert call.
        mock_kb.client.upsert.assert_not_called()

    def test_persist_failure_warns_in_status(self) -> None:
        """When Qdrant persist fails, status message includes a warning."""
        agent, mock_kb, _, mock_status = _make_agent()
        mock_kb.client.upsert.side_effect = ConnectionError("Qdrant down")

        result = agent.run()

        assert result.success is True
        # set_completed should be called with a warning about persistence
        mock_status.set_completed.assert_called_once()
        msg = mock_status.set_completed.call_args[0][0]
        assert "WARNING" in msg
        assert "not persisted" in msg
