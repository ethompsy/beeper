"""Integration tests for SandboxExecutorStep in the agent pipeline (Story 4.5)."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.sandbox_executor import SandboxExecutorStep


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


class TestSandboxExecutorPipelineIntegration:
    def test_sandbox_executor_is_step_9(self):
        """SandboxExecutorStep is step 9 (index 8) in _build_steps()."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 15
        assert isinstance(steps[10], SandboxExecutorStep)
        assert steps[10].name == "Sandbox Test Execution"

    def test_pipeline_metadata_shared(self):
        """SandboxExecutorStep receives the shared pipeline_metadata reference."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        sandbox_step = steps[10]
        assert sandbox_step.pipeline_metadata is agent._pipeline_metadata

    def test_sources_passed_to_sandbox_step(self):
        """SandboxExecutorStep receives the sources (Prometheus/Loki) clients."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        sandbox_step = steps[10]
        assert sandbox_step.sources is agent.sources

    def test_step_always_included_gates_internally(self):
        """SandboxExecutorStep is always in the pipeline; trust gating is internal."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent_tl1 = _make_agent(trust_level=1)
            steps_tl1 = agent_tl1._build_steps()

            agent_tl5 = _make_agent(trust_level=5)
            steps_tl5 = agent_tl5._build_steps()

        assert len(steps_tl1) == 15
        assert isinstance(steps_tl1[10], SandboxExecutorStep)
        assert len(steps_tl5) == 15
        assert isinstance(steps_tl5[10], SandboxExecutorStep)

    def test_step_between_test_planner_and_pr_generator(self):
        """SandboxExecutorStep is between TestPlannerStep and PRGeneratorStep."""
        from beeper_investigator.remediation.pr_generator import PRGeneratorStep
        from beeper_investigator.remediation.test_planner import TestPlannerStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert isinstance(steps[9], TestPlannerStep)
        assert isinstance(steps[10], SandboxExecutorStep)
        # MetricVerifierStep at index 10, PRGeneratorStep at index 11
        assert isinstance(steps[12], PRGeneratorStep)

    def test_total_pipeline_length_is_14(self):
        """Pipeline has exactly 15 steps (8 core + 7 remediation)."""
        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        assert len(steps) == 15

    def test_step_protocol_compliance(self):
        """SandboxExecutorStep implements InvestigationStep protocol."""
        from beeper_investigator.steps import InvestigationStep

        with patch("beeper_investigator.remediation.pr_generator.RepositoryLookup"):
            agent = _make_agent()
            steps = agent._build_steps()

        sandbox_step = steps[10]
        assert isinstance(sandbox_step, InvestigationStep)
