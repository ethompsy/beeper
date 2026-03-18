"""Integration tests for ProvenFixAccumulatorStep in the agent pipeline (Story 4.8)."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.proven_fix_accumulator import (
    ProvenFixAccumulatorStep,
)


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


class TestProvenFixPipelineIntegration:
    def test_proven_fix_is_step_13(self):
        """ProvenFixAccumulatorStep is step 13 (index 12) in _build_steps()."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 15
        assert isinstance(steps[14], ProvenFixAccumulatorStep)
        assert steps[14].name == "Proven Fix Accumulation"

    def test_pipeline_metadata_shared(self):
        """ProvenFixAccumulatorStep receives the shared pipeline_metadata reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        proven_fix_step = steps[14]
        assert proven_fix_step.pipeline_metadata is agent._pipeline_metadata

    def test_kb_client_shared(self):
        """ProvenFixAccumulatorStep receives the shared kb_client reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        proven_fix_step = steps[14]
        assert proven_fix_step.kb_client is agent.kb_client

    def test_step_always_included(self):
        """ProvenFixAccumulatorStep is always in the pipeline at all trust levels."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent_tl1 = _make_agent(trust_level=1)
            steps_tl1 = agent_tl1._build_steps()

            agent_tl5 = _make_agent(trust_level=5)
            steps_tl5 = agent_tl5._build_steps()

        assert len(steps_tl1) == 15
        assert isinstance(steps_tl1[14], ProvenFixAccumulatorStep)
        assert len(steps_tl5) == 15
        assert isinstance(steps_tl5[14], ProvenFixAccumulatorStep)

    def test_step_after_trust_gate(self):
        """ProvenFixAccumulatorStep comes after TrustGateStep (last step)."""
        from beeper_investigator.remediation.trust_gate import TrustGateStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[13], TrustGateStep)
        assert isinstance(steps[14], ProvenFixAccumulatorStep)

    def test_total_pipeline_length_is_14(self):
        """Pipeline has exactly 15 steps (8 core + 7 remediation)."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 15

    def test_step_protocol_compliance(self):
        """ProvenFixAccumulatorStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        proven_fix_step = steps[14]
        assert isinstance(proven_fix_step, InvestigationStep)
