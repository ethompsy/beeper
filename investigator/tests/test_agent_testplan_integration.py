"""Tests for TestPlannerStep integration in agent pipeline (Story 4.3)."""

from unittest.mock import MagicMock

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.test_planner import TestPlannerStep


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


class TestTestPlannerInPipeline:
    """Verify TestPlannerStep is integrated in the agent pipeline."""

    def test_testplanner_step_is_step_8(self):
        """TestPlannerStep is the 8th step in the pipeline."""
        agent = _make_agent()
        steps = agent._build_steps()

        assert len(steps) == 9
        assert isinstance(steps[7], TestPlannerStep)
        assert steps[7].name == "Test Plan Design"

    def test_pipeline_metadata_shared(self):
        """TestPlannerStep receives shared pipeline_metadata."""
        agent = _make_agent()
        steps = agent._build_steps()

        testplan_step = steps[7]
        assert testplan_step.pipeline_metadata is agent._pipeline_metadata

    def test_step_always_included_regardless_of_trust_level(self):
        """TestPlannerStep is always included, even at TL1."""
        for tl in [1, 2, 3, 4, 5]:
            ctx = InvestigationContext(
                investigation_id="test-tl",
                namespace="default",
                condition="error",
                service="auth",
                severity="high",
                trust_level=tl,
                confidence_threshold=0.85,
            )
            agent = _make_agent(context=ctx)
            steps = agent._build_steps()

            # TestPlannerStep should always be present
            testplan_steps = [s for s in steps if isinstance(s, TestPlannerStep)]
            assert len(testplan_steps) == 1, f"Missing at TL{tl}"

    def test_step_protocol_compliance(self):
        """TestPlannerStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        agent = _make_agent()
        steps = agent._build_steps()
        testplan_step = steps[7]

        assert isinstance(testplan_step, InvestigationStep)
        assert hasattr(testplan_step, "name")
        assert hasattr(testplan_step, "execute")
        assert callable(testplan_step.execute)
