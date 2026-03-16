"""Advisory test plan generation step.

Synthesizes an advisory test plan from the RCA hypothesis in pipeline_metadata,
providing SREs with numbered, actionable verification steps regardless of
trust level or sandbox availability (Story 4.3).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

VALID_VERIFICATION_TYPES = frozenset({
    "metric_check",
    "log_inspection",
    "api_probe",
    "health_check",
    "manual_verification",
})

_TEST_PLAN_SYSTEM_PROMPT = """\
You are a senior SRE designing a verification test plan for a root cause \
hypothesis. The test plan must give an on-call engineer clear, numbered, \
actionable steps to confirm or refute the hypothesis.

Respond with ONLY a JSON object:
{"hypothesis_statement": "restate the hypothesis concisely",
 "verification_steps": [
   {"step_number": 1,
    "title": "short title",
    "description": "detailed description of what to do",
    "action": "specific command, query, or check to perform",
    "expected_outcome": "what result confirms the hypothesis",
    "metric_or_endpoint": "specific metric name, log query, or endpoint",
    "verification_type": "metric_check"|"log_inspection"|"api_probe"\
|"health_check"|"manual_verification"}
 ],
 "expected_outcomes": ["outcome 1", "outcome 2"],
 "metrics_to_watch": ["metric.name.1", "metric.name.2"],
 "estimated_duration_minutes": 15}

Rules:
- Each step must reference a specific metric, endpoint, or log pattern
- Steps must be ordered logically (observe → correlate → verify)
- verification_type must be one of: metric_check, log_inspection, api_probe, \
health_check, manual_verification
- Include at least one metric_check step and one outcome that directly \
validates the hypothesis
- estimated_duration_minutes: realistic total time for all steps
- Be specific: use real metric names, PromQL patterns, or log queries \
relevant to the service and condition"""

_TEST_PLAN_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Namespace: {namespace}
Severity: {severity}

Root cause hypothesis: {hypothesis}
Confidence level: {confidence_level} ({confidence_percentage}%)

Supporting evidence:
{supporting_evidence}

Alternative hypotheses:
{alternative_hypotheses}

Signal context:
{signal_context}"""


@dataclass
class TestPlanStep:
    """Individual verification step in an advisory test plan."""

    step_number: int
    title: str
    description: str
    action: str
    expected_outcome: str
    metric_or_endpoint: str
    verification_type: str


@dataclass
class AdvisoryTestPlan:
    """Complete advisory test plan for verifying an RCA hypothesis."""

    hypothesis_statement: str
    confidence_level: str
    confidence_percentage: int
    verification_steps: list[TestPlanStep] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    metrics_to_watch: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 15
    promotable_to_sandbox: bool = True


class TestPlannerStep:
    """Generate advisory test plan from RCA hypothesis."""

    name: str = "Test Plan Design"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Generate advisory test plan."""
        self.status_updater.update_message("Generating advisory test plan")
        logger.info(
            "Starting test plan generation for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        # Extract hypothesis from pipeline metadata
        hypothesis_context = self._extract_hypothesis_context()
        if hypothesis_context is None:
            logger.info("No RCA hypothesis available — skipping test plan generation")
            return StepResult(
                success=True,
                summary="No RCA hypothesis available — test plan generation skipped",
                data={
                    "test_plan_generated": False,
                    "skip_reason": "no_hypothesis",
                },
            )

        # Resolve model name once for both LLM call and result metadata
        model_name = self._get_model_name()

        # Generate test plan via LLM
        self.status_updater.update_message("Designing verification steps")
        try:
            plan = self._generate_test_plan(hypothesis_context, model_name)
        except Exception as exc:
            logger.warning("Test plan generation failed: %s", exc)
            return StepResult(
                success=True,
                summary=f"Test plan generation failed: {exc}",
                data={
                    "test_plan_generated": False,
                    "skip_reason": "generation_failed",
                    "test_plan_model_tier": "remediation",
                    "test_plan_model_used": model_name,
                },
            )

        # Build result data
        steps_data = [
            {
                "step_number": s.step_number,
                "title": s.title,
                "description": s.description,
                "action": s.action,
                "expected_outcome": s.expected_outcome,
                "metric_or_endpoint": s.metric_or_endpoint,
                "verification_type": s.verification_type,
                "status": "pending",
            }
            for s in plan.verification_steps
        ]

        summary = (
            f"Advisory test plan generated: {len(plan.verification_steps)} "
            f"verification steps for hypothesis "
            f"'{plan.hypothesis_statement[:80]}' "
            f"(confidence: {plan.confidence_level})"
        )

        logger.info(
            "Test plan generated: steps=%d hypothesis='%s' confidence=%s",
            len(plan.verification_steps),
            plan.hypothesis_statement[:80],
            plan.confidence_level,
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "test_plan_generated": True,
                "hypothesis_statement": plan.hypothesis_statement,
                "confidence_level": plan.confidence_level,
                "confidence_percentage": plan.confidence_percentage,
                "verification_steps": steps_data,
                "expected_outcomes": plan.expected_outcomes,
                "metrics_to_watch": plan.metrics_to_watch,
                "estimated_duration_minutes": plan.estimated_duration_minutes,
                "promotable_to_sandbox": plan.promotable_to_sandbox,
                "steps_total": len(plan.verification_steps),
                "test_plan_model_tier": "remediation",
                "test_plan_model_used": model_name,
            },
        )

    # ── Hypothesis extraction ──────────────────────────────

    def _extract_hypothesis_context(self) -> dict[str, Any] | None:
        """Extract RCA hypothesis data from pipeline_metadata."""
        hypothesis = self.pipeline_metadata.get("root_cause_hypothesis")
        if not hypothesis:
            return None

        return {
            "root_cause_hypothesis": hypothesis,
            "confidence_level": self.pipeline_metadata.get("confidence_level", "unknown"),
            "confidence_percentage": self.pipeline_metadata.get("confidence_percentage", 0),
            "supporting_evidence": self.pipeline_metadata.get("supporting_evidence", []),
            "alternative_hypotheses": self.pipeline_metadata.get("alternative_hypotheses", []),
            "additional_data_needs": self.pipeline_metadata.get("additional_data_needs", []),
            "signal_summary": self.pipeline_metadata.get("signal_summary", ""),
            "service_dependency_chain": self.pipeline_metadata.get("service_dependency_chain", []),
            "layers_queried": self.pipeline_metadata.get("layers_queried", []),
        }

    # ── LLM test plan generation ───────────────────────────

    def _generate_test_plan(
        self, hypothesis_context: dict[str, Any], model_name: str | None = None,
    ) -> AdvisoryTestPlan:
        """Use LLM to generate an advisory test plan."""
        messages = self._build_plan_messages(hypothesis_context)

        raw = self.llm_client.complete_sync(
            messages,
            max_tokens=2048,
            temperature=0.0,
            model=model_name,
        )

        return self._parse_test_plan_response(
            raw,
            hypothesis_context.get("confidence_level", "unknown"),
            hypothesis_context.get("confidence_percentage", 0),
        )

    def _build_plan_messages(
        self, hypothesis_context: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Build LLM messages for test plan generation."""
        evidence = hypothesis_context.get("supporting_evidence", [])
        evidence_str = "\n".join(f"- {e}" for e in evidence) if evidence else "None available"

        alternatives = hypothesis_context.get("alternative_hypotheses", [])
        if alternatives:
            alt_parts = []
            for alt in alternatives:
                if isinstance(alt, dict):
                    desc = alt.get("description", str(alt))
                    conf = alt.get("confidence_percentage", "?")
                    alt_parts.append(f"- {desc} ({conf}%)")
                else:
                    alt_parts.append(f"- {alt}")
            alt_str = "\n".join(alt_parts)
        else:
            alt_str = "None identified"

        signal_parts = []
        if hypothesis_context.get("signal_summary"):
            signal_parts.append(f"Summary: {hypothesis_context['signal_summary']}")
        if hypothesis_context.get("service_dependency_chain"):
            chain = hypothesis_context["service_dependency_chain"]
            signal_parts.append(f"Dependency chain: {' → '.join(str(s) for s in chain)}")
        if hypothesis_context.get("layers_queried"):
            layers = hypothesis_context["layers_queried"]
            signal_parts.append(
                f"Layers queried: {', '.join(str(v) for v in layers)}"
            )
        signal_str = "\n".join(signal_parts) if signal_parts else "None available"

        user_content = _TEST_PLAN_USER_TEMPLATE.format(
            condition=self.context.condition,
            service=self.context.service,
            namespace=self.context.namespace,
            severity=self.context.severity,
            hypothesis=hypothesis_context["root_cause_hypothesis"],
            confidence_level=hypothesis_context.get("confidence_level", "unknown"),
            confidence_percentage=hypothesis_context.get("confidence_percentage", 0),
            supporting_evidence=evidence_str,
            alternative_hypotheses=alt_str,
            signal_context=signal_str,
        )
        return [
            {"role": "system", "content": _TEST_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_test_plan_response(
        self,
        raw: str,
        confidence_level: str,
        confidence_percentage: int,
    ) -> AdvisoryTestPlan:
        """Parse LLM response into AdvisoryTestPlan."""
        match = _CODE_FENCE_RE.search(raw)
        text = match.group(1) if match else raw

        try:
            data: dict[str, Any] = json.loads(text.strip())
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Failed to parse test plan response: %s (text: %.200s)",
                exc,
                text.strip(),
            )
            return self._fallback_plan(confidence_level, confidence_percentage)

        # Parse verification steps
        raw_steps = data.get("verification_steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            logger.warning("No verification steps in LLM response, using fallback")
            return self._fallback_plan(confidence_level, confidence_percentage)

        steps: list[TestPlanStep] = []
        for i, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                logger.warning(
                    "Skipping non-dict verification step at index %d: %s",
                    i, type(s).__name__,
                )
                continue

            vtype = str(s.get("verification_type", "manual_verification")).lower()
            if vtype not in VALID_VERIFICATION_TYPES:
                vtype = "manual_verification"

            steps.append(TestPlanStep(
                step_number=s.get("step_number", i + 1),
                title=str(s.get("title", f"Step {i + 1}")),
                description=str(s.get("description", "")),
                action=str(s.get("action", "")),
                expected_outcome=str(s.get("expected_outcome", "")),
                metric_or_endpoint=str(s.get("metric_or_endpoint", "")),
                verification_type=vtype,
            ))

        hypothesis_statement = str(data.get(
            "hypothesis_statement",
            self.pipeline_metadata.get("root_cause_hypothesis", "Unknown hypothesis"),
        ))

        expected_outcomes = data.get("expected_outcomes", [])
        if not isinstance(expected_outcomes, list):
            expected_outcomes = []

        metrics_to_watch = data.get("metrics_to_watch", [])
        if not isinstance(metrics_to_watch, list):
            metrics_to_watch = []

        duration = data.get("estimated_duration_minutes", 15)
        try:
            duration = max(1, int(duration))
        except (ValueError, TypeError):
            duration = 15

        return AdvisoryTestPlan(
            hypothesis_statement=hypothesis_statement,
            confidence_level=confidence_level,
            confidence_percentage=confidence_percentage,
            verification_steps=steps,
            expected_outcomes=[str(o) for o in expected_outcomes],
            metrics_to_watch=[str(m) for m in metrics_to_watch],
            estimated_duration_minutes=duration,
            promotable_to_sandbox=True,
        )

    def _fallback_plan(
        self, confidence_level: str, confidence_percentage: int
    ) -> AdvisoryTestPlan:
        """Return a minimal fallback plan when LLM parsing fails."""
        hypothesis = self.pipeline_metadata.get(
            "root_cause_hypothesis", "Unknown hypothesis"
        )
        return AdvisoryTestPlan(
            hypothesis_statement=hypothesis,
            confidence_level=confidence_level,
            confidence_percentage=confidence_percentage,
            verification_steps=[
                TestPlanStep(
                    step_number=1,
                    title="Manual investigation required",
                    description=(
                        "Automated test plan generation failed. "
                        "Manually investigate the root cause hypothesis."
                    ),
                    action="Review investigation findings and verify hypothesis manually",
                    expected_outcome="Hypothesis confirmed or refuted through manual analysis",
                    metric_or_endpoint="N/A",
                    verification_type="manual_verification",
                ),
            ],
            expected_outcomes=["Hypothesis confirmed or refuted through manual analysis"],
            metrics_to_watch=[],
            estimated_duration_minutes=30,
            promotable_to_sandbox=True,
        )

    # ── Helpers ─────────────────────────────────────────────

    def _get_model_name(self) -> str | None:
        """Get the model name for remediation tier, with fallback to deep_rca."""
        for tier in ("remediation", "deep_rca"):
            try:
                model = self.llm_client.select_model(tier)
                if model is not None:
                    return model
            except (KeyError, ValueError, AttributeError):
                logger.debug("Model tier '%s' not available, trying next", tier)
        return None
