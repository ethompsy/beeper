"""Investigation context for the Beeper investigator agent.

Bundles all investigation-specific configuration read from environment
variables injected by the operator's K8s Job spec.
"""

import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class InvestigationContext:
    """Immutable context for a single investigation run.

    All fields are populated from environment variables set by the operator
    when spawning the investigator Job.
    """

    investigation_id: str
    namespace: str
    condition: str
    service: str
    severity: str
    trust_level: int = 1
    confidence_threshold: float = 0.9

    @classmethod
    def from_env(cls) -> "InvestigationContext":
        """Build context from environment variables.

        Required: INVESTIGATION_ID, INVESTIGATION_NAMESPACE
        Optional (with defaults): INVESTIGATION_CONDITION,
        INVESTIGATION_SERVICE, INVESTIGATION_SEVERITY

        Returns:
            Populated InvestigationContext.

        Raises:
            SystemExit: If required variables are missing.
        """
        investigation_id = os.environ.get("INVESTIGATION_ID", "")
        namespace = os.environ.get("INVESTIGATION_NAMESPACE", "")

        if not investigation_id:
            print(
                json.dumps({
                    "level": "ERROR",
                    "message": "Required environment variable INVESTIGATION_ID is not set",
                }),
                file=sys.stderr,
            )
            sys.exit(1)

        if not namespace:
            print(
                json.dumps({
                    "level": "ERROR",
                    "message": "Required environment variable INVESTIGATION_NAMESPACE is not set",
                }),
                file=sys.stderr,
            )
            sys.exit(1)

        # Trust level: 1-5, defaults to 1 (advisory only)
        trust_level_raw = os.environ.get("INVESTIGATION_TRUST_LEVEL", "1")
        try:
            trust_level = max(1, min(5, int(trust_level_raw)))
        except (ValueError, TypeError):
            trust_level = 1

        # Confidence threshold: 0.0-1.0, defaults to 0.9 (90%)
        threshold_raw = os.environ.get("INVESTIGATION_CONFIDENCE_THRESHOLD", "0.9")
        try:
            confidence_threshold = max(0.0, min(1.0, float(threshold_raw)))
        except (ValueError, TypeError):
            confidence_threshold = 0.9

        return cls(
            investigation_id=investigation_id,
            namespace=namespace,
            condition=os.environ.get("INVESTIGATION_CONDITION", "unknown"),
            service=os.environ.get("INVESTIGATION_SERVICE", "unknown"),
            severity=os.environ.get("INVESTIGATION_SEVERITY", "medium"),
            trust_level=trust_level,
            confidence_threshold=confidence_threshold,
        )
