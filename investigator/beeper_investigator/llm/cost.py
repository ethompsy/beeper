"""LLM cost tracking and calculation.

Tracks token usage and calculates costs per LLM call based on model pricing.
Costs are stored in integer cents to avoid floating-point precision issues.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (in USD)
LLM_PRICING: dict[str, dict[str, float]] = {
    # Anthropic models
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def calculate_call_cost(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Calculate cost of a single LLM call in USD.

    Args:
        model: Model identifier string.
        prompt_tokens: Number of input tokens used.
        completion_tokens: Number of output tokens generated.

    Returns:
        Cost in USD (float). Returns 0.0 for unknown models.
    """
    pricing = LLM_PRICING.get(model)
    if pricing is None:
        logger.warning("No pricing data for model '%s', cost recorded as $0", model)
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


@dataclass
class CallRecord:
    """Record of a single LLM call's cost."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    timestamp: float  # time.monotonic() for internal tracking
    wall_time: str  # ISO 8601 for persistence


@dataclass
class CostTracker:
    """Accumulates LLM costs across an investigation lifecycle.

    Tracks per-call costs, daily/monthly aggregates, and total spend.
    Uses in-memory tracking scoped to the pod lifecycle.
    """

    _calls: list[CallRecord] = field(default_factory=list)
    _total_cost_usd: float = field(default=0.0)
    _total_prompt_tokens: int = field(default=0)
    _total_completion_tokens: int = field(default=0)

    def record_call(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Record a single LLM call and its cost.

        Args:
            model: Model identifier.
            prompt_tokens: Input tokens consumed.
            completion_tokens: Output tokens generated.

        Returns:
            Cost of this call in USD.
        """
        cost = calculate_call_cost(model, prompt_tokens, completion_tokens)
        record = CallRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            timestamp=time.monotonic(),
            wall_time=datetime.now(timezone.utc).isoformat(),
        )
        self._calls.append(record)
        self._total_cost_usd += cost
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        return cost

    @property
    def total_cost_usd(self) -> float:
        """Total accumulated cost in USD."""
        return self._total_cost_usd

    @property
    def total_cost_cents(self) -> int:
        """Total accumulated cost in cents (integer)."""
        return int(self._total_cost_usd * 100)

    @property
    def total_prompt_tokens(self) -> int:
        """Total prompt tokens consumed."""
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        """Total completion tokens generated."""
        return self._total_completion_tokens

    @property
    def call_count(self) -> int:
        """Number of recorded calls."""
        return len(self._calls)

    def get_cost_stats(self) -> dict[str, Any]:
        """Return cost statistics for metadata propagation.

        Returns:
            Dict with total_cost_usd, total_cost_cents, token counts,
            call_count, and per-model breakdown.
        """
        per_model: dict[str, dict[str, Any]] = {}
        for call in self._calls:
            if call.model not in per_model:
                per_model[call.model] = {
                    "calls": 0,
                    "cost_usd": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            entry = per_model[call.model]
            entry["calls"] += 1
            entry["cost_usd"] += call.cost_usd
            entry["prompt_tokens"] += call.prompt_tokens
            entry["completion_tokens"] += call.completion_tokens

        return {
            "total_cost_usd": round(self._total_cost_usd, 6),
            "total_cost_cents": self.total_cost_cents,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "call_count": len(self._calls),
            "per_model": per_model,
        }

    def reset(self) -> None:
        """Clear all tracked cost data."""
        self._calls.clear()
        self._total_cost_usd = 0.0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
