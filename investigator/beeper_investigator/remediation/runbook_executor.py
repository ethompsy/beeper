"""Human-language runbook execution step.

Retrieves runbooks from KB, interprets steps via LLM, and executes
them gated by trust level and confidence threshold (Story 4.2).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.kb.schemas import SearchResult
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

RUNBOOK_MATCH_THRESHOLD = 0.75

_VALID_ACTION_TYPES = {"diagnostic_check", "cluster_action", "manual_step"}

_RUNBOOK_INTERPRET_SYSTEM_PROMPT = """\
You are a senior SRE interpreting a human-language runbook into structured \
executable steps. Each step in the runbook must be classified and mapped to \
an action type.

Respond with ONLY a JSON object:
{"steps": [
  {"step_number": 1,
   "original_text": "the original runbook step text",
   "action_type": "diagnostic_check"|"cluster_action"|"manual_step",
   "interpreted_action": "specific executable description",
   "confidence": 0.0-1.0,
   "k8s_resource": "resource type or null",
   "k8s_operation": "operation or null"}
]}

Action type rules:
- diagnostic_check: Read-only operations (check logs, view metrics, describe pods). \
Safe to execute at any trust level.
- cluster_action: Mutations (scale deployment, restart pod, apply config). \
Requires trust level gating.
- manual_step: Human judgment required (contact team, review code, make decision). \
Never auto-executed.

Rules:
- Map EVERY step from the runbook, in order
- confidence: how certain you are about the interpretation (0.0 = guess, 1.0 = exact)
- k8s_resource: the K8s resource type if applicable (deployment, pod, service, etc.)
- k8s_operation: the K8s operation if applicable (scale, restart, patch, delete, etc.)
- Set k8s_resource and k8s_operation to null for non-K8s steps
- Be conservative with action_type: when uncertain, classify as manual_step"""

_RUNBOOK_INTERPRET_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}

Runbook title: {runbook_title}

Runbook content:
{runbook_content}"""


@dataclass
class RunbookExecutionResult:
    """Result of executing interpreted runbook steps."""

    executed_steps: list[dict[str, Any]] = field(default_factory=list)
    failed_step: dict[str, Any] | None = None
    remaining_steps: list[dict[str, Any]] = field(default_factory=list)
    halted: bool = False
    advisory_only: bool = False
    advisory_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)


class RunbookExecutorStep:
    """Execute human-language runbooks from KB without DSL translation."""

    name: str = "Runbook Execution"

    def __init__(
        self,
        llm_client: LlmClient,
        kb_client: KBClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.kb_client = kb_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Run the runbook execution step."""
        self.status_updater.update_message("Searching for matching runbooks")
        logger.info(
            "Starting runbook execution for service=%s condition=%s trust_level=%d",
            self.context.service,
            self.context.condition,
            self.context.trust_level,
        )

        # Step 1: Search KB for matching runbooks
        results = self._search_runbooks()
        runbook = self._select_best_runbook(results)

        if runbook is None:
            logger.info("No matching runbook found for service=%s", self.context.service)
            return StepResult(
                success=True,
                summary="No matching runbook found",
                data={
                    "runbook_found": False,
                    "runbook_execution_skipped": True,
                },
            )

        runbook_title = runbook.get("title", "Untitled Runbook")
        runbook_content = runbook.get("content", "")
        runbook_id = runbook.get("entry_id", "unknown")

        self.status_updater.update_message(f"Interpreting runbook: {runbook_title}")
        logger.info("Found runbook '%s' (id=%s), interpreting steps", runbook_title, runbook_id)

        # Step 2: LLM interprets runbook steps
        try:
            interpreted_steps = self._interpret_runbook(runbook_content, runbook_title)
        except Exception as exc:
            logger.warning("Runbook interpretation failed: %s", exc)
            return StepResult(
                success=True,
                summary=f"Runbook '{runbook_title}' found but interpretation failed: {exc}",
                data={
                    "runbook_found": True,
                    "runbook_title": runbook_title,
                    "runbook_id": runbook_id,
                    "interpretation_failed": True,
                    "runbook_model_tier": "remediation",
                    "runbook_model_used": None,
                },
            )

        if not interpreted_steps:
            logger.warning("Runbook interpretation returned no steps")
            return StepResult(
                success=True,
                summary=f"Runbook '{runbook_title}' found but no steps could be interpreted",
                data={
                    "runbook_found": True,
                    "runbook_title": runbook_title,
                    "runbook_id": runbook_id,
                    "steps_total": 0,
                    "interpretation_failed": True,
                },
            )

        # Step 3: Execute steps gated by trust level
        self.status_updater.update_message(f"Executing runbook: {runbook_title}")
        exec_result = self._execute_steps(interpreted_steps)

        # Build summary
        steps_total = len(interpreted_steps)
        steps_executed = len(exec_result.executed_steps)
        steps_advisory = len(exec_result.advisory_actions)
        steps_blocked = len(exec_result.blocked_actions)

        if exec_result.halted:
            fs = exec_result.failed_step
            failed_num = fs.get("step_number", "?") if fs else "?"
            failed_err = fs.get("error", "unknown") if fs else "unknown"
            summary = (
                f"Runbook execution halted at step {failed_num}: {failed_err}"
            )
        else:
            summary = (
                f"Executed runbook '{runbook_title}': "
                f"{steps_executed}/{steps_total} steps"
                f" ({steps_advisory} advisory, {steps_blocked} blocked)"
            )

        return StepResult(
            success=not exec_result.halted,
            summary=summary,
            data={
                "runbook_found": True,
                "runbook_title": runbook_title,
                "runbook_id": runbook_id,
                "steps_total": steps_total,
                "steps_executed": steps_executed,
                "steps_advisory": steps_advisory,
                "steps_blocked": steps_blocked,
                "execution_halted": exec_result.halted,
                "failed_step_context": exec_result.failed_step,
                "remaining_steps": exec_result.remaining_steps,
                "advisory_actions": exec_result.advisory_actions,
                "execution_log": exec_result.executed_steps,
                "runbook_model_tier": "remediation",
                "runbook_model_used": self._get_model_name(),
            },
        )

    # ── KB search ──────────────────────────────────────────

    def _search_runbooks(self) -> list[SearchResult]:
        """Search KB for runbooks matching the current investigation."""
        query_text = f"{self.context.condition} {self.context.service}"
        try:
            embedding = self.llm_client.embed_sync(query_text)
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return []

        try:
            return self.kb_client.search_knowledge(
                query_vector=embedding,
                entry_type="runbook",
                service=self.context.service,
                limit=3,
            )
        except Exception as exc:
            logger.warning("KB runbook search failed: %s", exc)
            return []

    def _select_best_runbook(self, results: list[SearchResult]) -> dict[str, Any] | None:
        """Select the best matching runbook above threshold."""
        if not results:
            return None
        best = max(results, key=lambda r: r.score)
        if best.score < RUNBOOK_MATCH_THRESHOLD:
            logger.info(
                "Best runbook score %.3f below threshold %.3f",
                best.score,
                RUNBOOK_MATCH_THRESHOLD,
            )
            return None
        return best.payload

    # ── LLM interpretation ─────────────────────────────────

    def _interpret_runbook(
        self, runbook_content: str, runbook_title: str
    ) -> list[dict[str, Any]]:
        """Use LLM to interpret runbook steps into structured actions."""
        messages = self._build_interpret_messages(runbook_content, runbook_title)
        model_name = self._get_model_name()

        raw = self.llm_client.complete_sync(
            messages,
            max_tokens=2048,
            temperature=0.0,
            model=model_name,
        )

        parsed = self._parse_interpret_response(raw)
        steps = parsed.get("steps", [])
        if not isinstance(steps, list):
            logger.warning("LLM returned non-list steps: %s", type(steps))
            return []

        validated = self._validate_interpreted_steps(steps)

        # Log each interpreted step
        for step in validated:
            logger.info(
                "Interpreted runbook step: %s",
                json.dumps({
                    "step_number": step["step_number"],
                    "original_text": step["original_text"],
                    "action_type": step["action_type"],
                    "interpreted_action": step["interpreted_action"],
                    "confidence": step["confidence"],
                }),
            )

        return validated

    def _build_interpret_messages(
        self, runbook_content: str, runbook_title: str
    ) -> list[dict[str, str]]:
        """Build LLM messages for runbook interpretation."""
        user_content = _RUNBOOK_INTERPRET_USER_TEMPLATE.format(
            condition=self.context.condition,
            service=self.context.service,
            severity=self.context.severity,
            runbook_title=runbook_title,
            runbook_content=runbook_content,
        )
        return [
            {"role": "system", "content": _RUNBOOK_INTERPRET_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_interpret_response(self, raw: str) -> dict[str, Any]:
        """Parse LLM response, stripping markdown fences if present."""
        match = _CODE_FENCE_RE.search(raw)
        text = match.group(1) if match else raw
        try:
            result: dict[str, Any] = json.loads(text.strip())
            return result
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse runbook interpretation response")
            return {}

    def _validate_interpreted_steps(
        self, steps: list[Any]
    ) -> list[dict[str, Any]]:
        """Validate and normalize interpreted steps."""
        validated: list[dict[str, Any]] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            original_text = step.get("original_text", "")
            if not isinstance(original_text, str) or not original_text:
                continue

            action_type = str(step.get("action_type", "manual_step")).lower()
            if action_type not in _VALID_ACTION_TYPES:
                action_type = "manual_step"

            confidence = step.get("confidence", 0.5)
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (ValueError, TypeError):
                confidence = 0.5

            validated.append({
                "step_number": step.get("step_number", i + 1),
                "original_text": original_text,
                "action_type": action_type,
                "interpreted_action": str(step.get("interpreted_action", original_text)),
                "confidence": confidence,
                "k8s_resource": step.get("k8s_resource"),
                "k8s_operation": step.get("k8s_operation"),
            })

        return validated

    # ── Trust-gated execution ──────────────────────────────

    def _execute_steps(
        self, interpreted_steps: list[dict[str, Any]]
    ) -> RunbookExecutionResult:
        """Execute interpreted steps with trust-level gating."""
        result = RunbookExecutionResult(
            advisory_only=self.context.trust_level <= 2,
        )

        for i, step in enumerate(interpreted_steps):
            action_type = step["action_type"]
            confidence = step["confidence"]
            action_desc = step["interpreted_action"]
            step_num = step["step_number"]

            try:
                if action_type == "diagnostic_check":
                    # Always safe — read-only
                    log_entry = {
                        **step,
                        "status": "executed",
                        "execution_type": "diagnostic",
                    }
                    logger.info(
                        "Diagnostic check (step %d): %s", step_num, action_desc,
                    )
                    result.executed_steps.append(log_entry)

                elif action_type == "cluster_action":
                    if self.context.trust_level <= 2:
                        # Advisory only
                        advisory_msg = (
                            f"Advisory: would execute '{action_desc}' at TL3+"
                        )
                        logger.info(
                            "Advisory (step %d, TL%d): %s",
                            step_num, self.context.trust_level, action_desc,
                        )
                        result.advisory_actions.append(advisory_msg)
                        result.executed_steps.append({
                            **step,
                            "status": "advisory",
                            "execution_type": "advisory",
                            "message": advisory_msg,
                        })
                    elif confidence >= self.context.confidence_threshold:
                        # Approved for execution (actual K8s execution deferred to Story 4-5)
                        logger.info(
                            "Approved (step %d, TL%d, confidence=%.2f): %s",
                            step_num, self.context.trust_level, confidence, action_desc,
                        )
                        result.executed_steps.append({
                            **step,
                            "status": "approved",
                            "execution_type": "approved_for_execution",
                        })
                    else:
                        # Blocked — confidence below threshold
                        blocked_msg = (
                            f"Blocked: confidence {confidence:.2f} "
                            f"below threshold {self.context.confidence_threshold:.2f}"
                        )
                        logger.info(
                            "Blocked (step %d): %s — %s",
                            step_num, action_desc, blocked_msg,
                        )
                        result.blocked_actions.append(blocked_msg)
                        result.executed_steps.append({
                            **step,
                            "status": "blocked",
                            "execution_type": "blocked",
                            "message": blocked_msg,
                        })

                elif action_type == "manual_step":
                    # Never auto-execute
                    logger.info(
                        "Manual step (step %d): requires human action — %s",
                        step_num, action_desc,
                    )
                    result.executed_steps.append({
                        **step,
                        "status": "manual",
                        "execution_type": "requires_human",
                    })

                else:
                    # Unknown action type — treat as manual
                    logger.warning(
                        "Unknown action type '%s' (step %d), treating as manual",
                        action_type, step_num,
                    )
                    result.executed_steps.append({
                        **step,
                        "status": "manual",
                        "execution_type": "unknown_type_fallback",
                    })

            except Exception as exc:
                # Step failure — halt immediately
                logger.error(
                    "Runbook step %d failed: %s", step_num, exc,
                )
                result.halted = True
                result.failed_step = {
                    **step,
                    "status": "failed",
                    "error": str(exc),
                }
                result.remaining_steps = interpreted_steps[i + 1:]
                return result

        return result

    # ── Helpers ─────────────────────────────────────────────

    def _get_model_name(self) -> str | None:
        """Get the model name for remediation tier, with fallback."""
        try:
            return self.llm_client.select_model("remediation")
        except Exception:
            try:
                return self.llm_client.select_model("deep_rca")
            except Exception:
                return None
