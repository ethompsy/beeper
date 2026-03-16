"""Integration tests for MetricVerifierStep in the agent pipeline (Story 4.6)."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.metric_verifier import MetricVerifierStep


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


class TestMetricVerifierPipelineIntegration:
    def test_metric_verifier_is_step_10(self):
        """MetricVerifierStep is step 10 (index 9) in _build_steps()."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 11
        assert isinstance(steps[9], MetricVerifierStep)
        assert steps[9].name == "Post-Fix Metric Verification"

    def test_pipeline_metadata_shared(self):
        """MetricVerifierStep receives the shared pipeline_metadata reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        verifier_step = steps[9]
        assert verifier_step.pipeline_metadata is agent._pipeline_metadata

    def test_sources_passed_to_verifier_step(self):
        """MetricVerifierStep receives the sources (Prometheus/Loki) clients."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        verifier_step = steps[9]
        assert verifier_step.sources is agent.sources

    def test_step_always_included_gates_internally(self):
        """MetricVerifierStep is always in pipeline; trust gating is internal."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent_tl1 = _make_agent(trust_level=1)
            steps_tl1 = agent_tl1._build_steps()

            agent_tl5 = _make_agent(trust_level=5)
            steps_tl5 = agent_tl5._build_steps()

        assert len(steps_tl1) == 11
        assert isinstance(steps_tl1[9], MetricVerifierStep)
        assert len(steps_tl5) == 11
        assert isinstance(steps_tl5[9], MetricVerifierStep)

    def test_step_between_sandbox_and_pr_generator(self):
        """MetricVerifierStep is between SandboxExecutorStep and PRGeneratorStep."""
        from beeper_investigator.remediation.pr_generator import PRGeneratorStep
        from beeper_investigator.remediation.sandbox_executor import SandboxExecutorStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[8], SandboxExecutorStep)
        assert isinstance(steps[9], MetricVerifierStep)
        assert isinstance(steps[10], PRGeneratorStep)

    def test_total_pipeline_length_is_11(self):
        """Pipeline has exactly 11 steps after adding MetricVerifierStep."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 11

    def test_step_protocol_compliance(self):
        """MetricVerifierStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        verifier_step = steps[9]
        assert isinstance(verifier_step, InvestigationStep)
