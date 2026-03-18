"""Integration tests for PRGeneratorStep in the agent pipeline."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.pr_generator import PRGeneratorStep


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


class TestPRGeneratorPipelineIntegration:
    def test_pr_generator_is_step_11(self):
        """PRGeneratorStep is step 11 (index 10) in _build_steps()."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 16
        assert isinstance(steps[13], PRGeneratorStep)
        assert steps[13].name == "PR Generation"

    def test_pipeline_metadata_shared_with_pr_step(self):
        """PRGeneratorStep receives the shared pipeline_metadata reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        pr_step = steps[13]
        assert pr_step.pipeline_metadata is agent._pipeline_metadata

    def test_step_always_included_gates_internally(self):
        """PRGeneratorStep is always in the pipeline; trust gating is internal."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent_tl1 = _make_agent(trust_level=1)
            steps_tl1 = agent_tl1._build_steps()

            agent_tl5 = _make_agent(trust_level=5)
            steps_tl5 = agent_tl5._build_steps()

        # Step is present regardless of trust level
        assert len(steps_tl1) == 16
        assert isinstance(steps_tl1[13], PRGeneratorStep)
        assert len(steps_tl5) == 16
        assert isinstance(steps_tl5[13], PRGeneratorStep)

    def test_step_order_after_metric_verifier(self):
        """PRGeneratorStep comes after MetricVerifierStep."""
        from beeper_investigator.remediation.metric_verifier import MetricVerifierStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[12], MetricVerifierStep)
        assert isinstance(steps[13], PRGeneratorStep)
