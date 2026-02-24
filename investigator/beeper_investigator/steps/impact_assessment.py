"""Customer impact assessment investigation step.

Assesses whether a detected condition impacts customers using a
lightweight LLM screening call (FR3, FR43).
"""

import json
import logging
import re

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an SRE impact assessment assistant. Given information about a detected \
condition, determine whether it impacts customers.

Respond with ONLY a JSON object:
{"customer_impacting": true|false|"unknown", "reasoning": "brief explanation"}

Rules:
- true: Condition affects customer-facing services, user experience, or data
- false: Condition is purely internal/infrastructure with no customer visibility
- "unknown": Insufficient information to determine impact"""

_USER_PROMPT_TEMPLATE = """\
Condition: {condition}
Service: {service}
Severity: {severity}"""

# Match JSON content within optional markdown code fences
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _parse_response(raw: str) -> dict:
    """Parse LLM response, stripping markdown fences if present."""
    # Try stripping code fences first
    match = _CODE_FENCE_RE.search(raw)
    text = match.group(1) if match else raw

    return json.loads(text.strip())


class CustomerImpactStep:
    """Assess whether a condition has customer impact.

    Uses a lightweight LLM model for fast, cheap screening.
    """

    name: str = "Customer Impact Assessment"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater

    def execute(self) -> StepResult:
        """Run the customer impact assessment."""
        self.status_updater.update_message("Assessing customer impact")
        logger.info(
            "Assessing customer impact for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_PROMPT_TEMPLATE.format(
                    condition=self.context.condition,
                    service=self.context.service,
                    severity=self.context.severity,
                ),
            },
        ]

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=256,
                temperature=0.0,
                model=self.llm_client.screening_model,
            )
        except Exception as exc:
            logger.warning("LLM call failed for impact assessment: %s", exc)
            return StepResult(
                success=False,
                summary="Customer impact assessment failed; defaulting to unknown",
                data={"customer_impacting": "unknown"},
                error=str(exc),
            )

        return self._parse_result(raw)

    def _parse_result(self, raw: str) -> StepResult:
        """Parse the LLM response into a StepResult."""
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM response as JSON: %s", raw)
            return StepResult(
                success=True,
                summary="Customer impact: unknown (parse failure)",
                data={"customer_impacting": "unknown", "reasoning": "LLM response could not be parsed"},
            )

        impact = parsed.get("customer_impacting", "unknown")
        reasoning = parsed.get("reasoning", "")

        # Normalize impact value (handle case variations from LLMs)
        impact_lower = str(impact).lower() if isinstance(impact, str) else impact
        if impact is True or impact_lower == "true":
            impact = True
        elif impact is False or impact_lower == "false":
            impact = False
        else:
            impact = "unknown"

        logger.info("Customer impact assessment: %s (reason: %s)", impact, reasoning)

        return StepResult(
            success=True,
            summary=f"Customer impact: {impact}",
            data={"customer_impacting": impact, "reasoning": reasoning},
        )
