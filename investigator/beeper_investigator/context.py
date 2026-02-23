"""Investigation context for the Beeper investigator agent.

Bundles all investigation-specific configuration read from environment
variables injected by the operator's K8s Job spec.
"""

import os
import sys
import json
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

    @classmethod
    def from_env(cls) -> "InvestigationContext":
        """Build context from environment variables.

        Required: INVESTIGATION_ID, INVESTIGATION_NAMESPACE
        Optional (with defaults): INVESTIGATION_CONDITION, INVESTIGATION_SERVICE, INVESTIGATION_SEVERITY

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

        return cls(
            investigation_id=investigation_id,
            namespace=namespace,
            condition=os.environ.get("INVESTIGATION_CONDITION", "unknown"),
            service=os.environ.get("INVESTIGATION_SERVICE", "unknown"),
            severity=os.environ.get("INVESTIGATION_SEVERITY", "medium"),
        )
