"""Tests for the investigation step pipeline in the agent."""

from unittest.mock import MagicMock

from beeper_investigator.agent import (
    InvestigationResult,
    InvestigatorAgent,
    SourceClients,
)
from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps import InvestigationStep, StepResult


def _make_agent() -> tuple[InvestigatorAgent, MagicMock, MagicMock, MagicMock]:
    """Build an agent with fully mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="inv-test-001",
        namespace="default",
        condition="CPU spike on checkout",
        service="payments",
        severity="high",
    )
    mock_kb = MagicMock()
    mock_kb.health_check.return_value = True
    mock_llm = MagicMock()
    mock_llm.test_connection.return_value = True
    mock_status = MagicMock()
    sources = SourceClients()

    agent = InvestigatorAgent(
        context=ctx,
        kb_client=mock_kb,
        llm_client=mock_llm,
        sources=sources,
        status_updater=mock_status,
    )
    return agent, mock_kb, mock_llm, mock_status


class _FakeStep:
    """A fake step for testing the pipeline."""

    def __init__(self, name: str, result: StepResult) -> None:
        self.name = name
        self._result = result
        self.executed = False

    def execute(self) -> StepResult:
        self.executed = True
        return self._result


class TestStepPipeline:
    """Tests for _run_steps with registered steps."""

    def test_no_steps_returns_success(self) -> None:
        """Agent with no steps returns success."""
        agent, *_ = _make_agent()
        agent.steps = []
        result = agent.run()
        assert result.success is True

    def test_single_step_executed(self) -> None:
        """A registered step is executed during run()."""
        agent, *_ = _make_agent()
        step = _FakeStep("test-step", StepResult(success=True, summary="done"))
        agent.steps = [step]

        result = agent.run()

        assert step.executed is True
        assert result.success is True
        assert "done" in result.summary

    def test_step_data_flows_to_metadata(self) -> None:
        """Step result data flows into InvestigationResult.metadata."""
        agent, *_ = _make_agent()
        step = _FakeStep(
            "impact",
            StepResult(success=True, summary="assessed", data={"customer_impacting": True}),
        )
        agent.steps = [step]

        result = agent.run()

        assert result.metadata["customer_impacting"] is True

    def test_multiple_steps_execute_in_order(self) -> None:
        """Multiple steps execute in registration order."""
        agent, _, _, mock_status = _make_agent()
        order: list[str] = []

        class _OrderStep:
            def __init__(self, name: str) -> None:
                self.name = name

            def execute(self) -> StepResult:
                order.append(self.name)
                return StepResult(success=True, summary=self.name)

        agent.steps = [_OrderStep("first"), _OrderStep("second"), _OrderStep("third")]

        agent.run()

        assert order == ["first", "second", "third"]

    def test_step_failure_is_non_fatal(self) -> None:
        """A failing step does not abort the pipeline."""
        agent, *_ = _make_agent()
        fail_step = _FakeStep(
            "failing",
            StepResult(success=False, summary="oops", error="something broke"),
        )
        ok_step = _FakeStep("ok", StepResult(success=True, summary="fine"))
        agent.steps = [fail_step, ok_step]

        result = agent.run()

        assert fail_step.executed is True
        assert ok_step.executed is True
        assert result.success is True

    def test_step_data_merged_across_steps(self) -> None:
        """Data from multiple steps is merged into metadata."""
        agent, *_ = _make_agent()
        s1 = _FakeStep("s1", StepResult(success=True, summary="a", data={"key1": "v1"}))
        s2 = _FakeStep("s2", StepResult(success=True, summary="b", data={"key2": "v2"}))
        agent.steps = [s1, s2]

        result = agent.run()

        assert result.metadata["key1"] == "v1"
        assert result.metadata["key2"] == "v2"

    def test_status_updater_reports_step_name(self) -> None:
        """Status updater is called with step name during execution."""
        agent, _, _, mock_status = _make_agent()
        step = _FakeStep("impact-check", StepResult(success=True, summary="ok"))
        agent.steps = [step]

        agent.run()

        messages = [c[0][0] for c in mock_status.update_message.call_args_list]
        assert any("impact-check" in m for m in messages)


class TestInvestigationResultMetadata:
    """Tests for InvestigationResult.metadata field."""

    def test_metadata_defaults_empty(self) -> None:
        """InvestigationResult.metadata defaults to empty dict."""
        result = InvestigationResult(success=True, summary="ok")
        assert result.metadata == {}

    def test_metadata_persisted_to_qdrant(self) -> None:
        """Metadata fields appear in Qdrant persist payload."""
        agent, mock_kb, *_ = _make_agent()
        step = _FakeStep(
            "impact",
            StepResult(success=True, summary="assessed", data={"customer_impacting": True}),
        )
        agent.steps = [step]

        agent.run()

        mock_kb.client.upsert.assert_called_once()
        payload = mock_kb.client.upsert.call_args[0][1][0].payload
        assert payload["customer_impacting"] is True

    def test_metadata_collision_with_reserved_key_is_skipped(self) -> None:
        """Step metadata that collides with reserved payload keys is skipped."""
        agent, mock_kb, *_ = _make_agent()
        step = _FakeStep(
            "bad-step",
            StepResult(
                success=True,
                summary="collides",
                data={"service": "OVERWRITTEN", "safe_key": "ok"},
            ),
        )
        agent.steps = [step]

        agent.run()

        mock_kb.client.upsert.assert_called_once()
        payload = mock_kb.client.upsert.call_args[0][1][0].payload
        # Reserved key should NOT be overwritten
        assert payload["service"] == "payments"
        # Non-reserved key should be present
        assert payload["safe_key"] == "ok"


class TestBuildStepsFailure:
    """Tests for _build_steps() error handling."""

    def test_import_error_in_build_steps_caught(self) -> None:
        """ImportError in _build_steps() is caught by run()."""
        agent, _, _, mock_status = _make_agent()
        # Leave steps as None so _build_steps() is called
        agent.steps = None

        from unittest.mock import patch

        with patch.object(agent, "_build_steps", side_effect=ImportError("no module")):
            result = agent.run()

        assert result.success is False
        assert "no module" in (result.error or "")
        mock_status.set_failed.assert_called_once()
