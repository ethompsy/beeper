"""Tests for RunbookExecutorStep integration in agent pipeline (Story 4.2)."""

from unittest.mock import MagicMock

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.runbook_executor import RunbookExecutorStep


def _make_agent(**overrides) -> InvestigatorAgent:
    """Create an InvestigatorAgent with mocked dependencies."""
    ctx = overrides.get("context", InvestigationContext(
        investigation_id="test-inv",
        namespace="default",
        condition="high_latency",
        service="payments",
        severity="high",
        trust_level=1,
        confidence_threshold=0.9,
    ))
    kb = overrides.get("kb_client", MagicMock(spec=KBClient))
    llm = overrides.get("llm_client", MagicMock(spec=LlmClient))
    sources = overrides.get("sources", SourceClients())
    status = overrides.get("status_updater", MagicMock(spec=InvestigationStatusUpdater))

    return InvestigatorAgent(
        context=ctx,
        kb_client=kb,
        llm_client=llm,
        sources=sources,
        status_updater=status,
    )


class TestRunbookInPipeline:
    """Verify RunbookExecutorStep is integrated in the agent pipeline."""

    def test_runbook_step_is_step_7(self):
        """RunbookExecutorStep is the 7th step in the pipeline."""
        agent = _make_agent()
        steps = agent._build_steps()

        assert len(steps) == 13
        assert isinstance(steps[6], RunbookExecutorStep)
        assert steps[6].name == "Runbook Execution"

    def test_pipeline_metadata_shared(self):
        """RunbookExecutorStep receives shared pipeline_metadata."""
        agent = _make_agent()
        steps = agent._build_steps()

        runbook_step = steps[6]
        assert runbook_step.pipeline_metadata is agent._pipeline_metadata

    def test_trust_level_flows_to_step(self):
        """Trust level from context flows through to runbook step."""
        ctx = InvestigationContext(
            investigation_id="test-tl",
            namespace="default",
            condition="error",
            service="auth",
            severity="high",
            trust_level=4,
            confidence_threshold=0.85,
        )
        agent = _make_agent(context=ctx)
        steps = agent._build_steps()

        runbook_step = steps[6]
        assert runbook_step.context.trust_level == 4
        assert runbook_step.context.confidence_threshold == 0.85

    def test_step_protocol_compliance(self):
        """RunbookExecutorStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        agent = _make_agent()
        steps = agent._build_steps()
        runbook_step = steps[6]

        assert isinstance(runbook_step, InvestigationStep)
        assert hasattr(runbook_step, "name")
        assert hasattr(runbook_step, "execute")
        assert callable(runbook_step.execute)
