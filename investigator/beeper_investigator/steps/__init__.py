"""Investigation step protocol and result types.

Each investigation step (stories 3.3-3.8) implements the InvestigationStep
protocol. Steps are executed sequentially by the agent pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class StepResult:
    """Outcome of a single investigation step."""

    success: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class InvestigationStep(Protocol):
    """Protocol for investigation steps."""

    name: str

    def execute(self) -> StepResult:
        """Run the step and return structured result."""
        ...
