"""Integration tests for TrustGateStep in the agent pipeline (Story 4.7)."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.trust_gate import TrustGateStep


def _make_agent(trust_level=3):
    """Create an InvestigatorAgent with mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=0.9,
    )
    kb = MagicMock(spec=KBClient)
    llm = MagicMock(spec=LlmClient)
    sources = SourceClients()
    status = MagicMock(spec=InvestigationStatusUpdater)

    with patch("beeper_investigator.agent.SpendingCapConfig") as mock_cap:
        mock_cap.from_env.return_value = MagicMock(enabled=False)
        agent = InvestigatorAgent(
            context=ctx,
            kb_client=kb,
            llm_client=llm,
            sources=sources,
            status_updater=status,
        )
    return agent


class TestTrustGatePipelineIntegration:
    def test_trust_gate_is_step_12(self):
        """TrustGateStep is step 12 (index 11) in _build_steps()."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 12
        assert isinstance(steps[11], TrustGateStep)
        assert steps[11].name == "Trust Gate Evaluation"

    def test_pipeline_metadata_shared(self):
        """TrustGateStep receives the shared pipeline_metadata reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        trust_gate_step = steps[11]
        assert trust_gate_step.pipeline_metadata is agent._pipeline_metadata

    def test_step_always_included_gates_internally(self):
        """TrustGateStep is always in the pipeline; review is internal."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent_tl1 = _make_agent(trust_level=1)
            steps_tl1 = agent_tl1._build_steps()

            agent_tl5 = _make_agent(trust_level=5)
            steps_tl5 = agent_tl5._build_steps()

        assert len(steps_tl1) == 12
        assert isinstance(steps_tl1[11], TrustGateStep)
        assert len(steps_tl5) == 12
        assert isinstance(steps_tl5[11], TrustGateStep)

    def test_step_after_pr_generator(self):
        """TrustGateStep comes after PRGeneratorStep (last step)."""
        from beeper_investigator.remediation.pr_generator import PRGeneratorStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[10], PRGeneratorStep)
        assert isinstance(steps[11], TrustGateStep)

    def test_total_pipeline_length_is_12(self):
        """Pipeline has exactly 12 steps (6 core + 6 remediation)."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 12

    def test_step_protocol_compliance(self):
        """TrustGateStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        trust_gate_step = steps[11]
        assert isinstance(trust_gate_step, InvestigationStep)

    def test_trust_gate_is_last_step(self):
        """TrustGateStep is the last step in the pipeline."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[-1], TrustGateStep)
