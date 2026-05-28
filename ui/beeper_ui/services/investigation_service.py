"""Investigation service for fetching investigation status from the operator."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"


@dataclass
class Investigation:
    """An active or completed investigation."""

    id: str
    status: str
    service: str
    severity: str
    condition: str
    started_at: str | None = None
    completed_at: str | None = None
    triggered_at: str | None = None
    workflow_state: str | None = None
    workflow_state_changed_at: str | None = None
    remediation_status: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Investigation":
        """Create Investigation from dictionary."""
        return cls(
            id=data["id"],
            status=data["status"],
            service=data["service"],
            severity=data["severity"],
            condition=data["condition"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            triggered_at=data.get("triggered_at"),
            workflow_state=data.get("workflow_state"),
            workflow_state_changed_at=data.get("workflow_state_changed_at"),
        )


@dataclass
class InvestigationDetail(Investigation):
    """Extended investigation with detail fields."""

    message: str | None = None
    error: str | None = None
    job_name: str | None = None
    # Count of correlated signals gathered during the investigation. Surfaced in
    # the summary header (Story 4.2, FR23) immediately from server data — no SSE.
    signal_count: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvestigationDetail":
        """Create InvestigationDetail from dictionary."""
        return cls(
            id=data["id"],
            status=data["status"],
            service=data["service"],
            severity=data["severity"],
            condition=data["condition"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            triggered_at=data.get("triggered_at"),
            message=data.get("message"),
            error=data.get("error"),
            job_name=data.get("job_name"),
            workflow_state=data.get("workflow_state"),
            workflow_state_changed_at=data.get("workflow_state_changed_at"),
            signal_count=data.get("signal_count"),
        )


class InvestigationService:
    """Service for fetching investigation status from the operator API."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        """Initialize the investigation service.

        Args:
            operator_url: Base URL of the operator API.
            timeout: HTTP request timeout in seconds.
        """
        self.operator_url = operator_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._qdrant_client: QdrantClient | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    @property
    def qdrant_client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            self._qdrant_client = QdrantClient(host=host, port=port)
        return self._qdrant_client

    def close(self) -> None:
        """Close the HTTP and Qdrant clients."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None

    def list_investigations(
        self,
        status: str | None = None,
        service: str | None = None,
        severity: str | None = None,
    ) -> list[Investigation]:
        """Fetch investigations from the operator with optional filtering.

        Args:
            status: Filter by status (investigating, awaiting_confirmation, completed, failed).
            service: Filter by service name.
            severity: Filter by severity (low, medium, high, critical).

        Returns:
            List of Investigation objects.

        Raises:
            InvestigationServiceError: If the operator cannot be reached or returns an error.
        """
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if service:
            params["service"] = service
        if severity:
            params["severity"] = severity

        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/investigations",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return [Investigation.from_dict(inv) for inv in data]
        except httpx.TimeoutException as e:
            logger.warning("Timeout connecting to operator for investigations: %s", e)
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error for investigations: %s",
                e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning("Failed to connect to operator for investigations: %s", e)
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def get_investigation(
        self, investigation_id: str
    ) -> InvestigationDetail | None:
        """Fetch a single investigation by ID from the operator.

        Args:
            investigation_id: The investigation CRD name.

        Returns:
            InvestigationDetail if found, None if 404.

        Raises:
            InvestigationServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}",
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return InvestigationDetail.from_dict(response.json())
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout connecting to operator for investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error for investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def get_investigation_findings(
        self, investigation_id: str
    ) -> dict[str, Any]:
        """Fetch investigation findings from Qdrant.

        Retrieves pipeline metadata (step results) accumulated during
        the investigation from the Qdrant investigations collection.

        Args:
            investigation_id: The investigation ID to look up.

        Returns:
            Dict of pipeline metadata, or empty dict if not found.
        """
        try:
            results, _ = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return {}
            return dict(results[0].payload or {})
        except UnexpectedResponse as e:
            logger.warning(
                "Qdrant query failed for investigation findings %s: %s",
                investigation_id, e,
            )
            return {}
        except Exception as e:
            logger.warning(
                "Failed to fetch investigation findings %s: %s",
                investigation_id, e,
            )
            return {}


    def get_remediation_progress(
        self, investigation_id: str
    ) -> dict[str, Any] | None:
        """Get remediation progress for an investigation.

        Fetches findings from Qdrant and computes remediation status.

        Args:
            investigation_id: The investigation ID.

        Returns:
            Remediation status dict or None if no remediation.
        """
        findings = self.get_investigation_findings(investigation_id)
        return compute_remediation_status(findings)

    def confirm_resolution(
        self, investigation_id: str, comment: str | None = None
    ) -> bool:
        """Confirm an investigation's resolution recommendation.

        Args:
            investigation_id: The investigation CRD name.
            comment: Optional comment from the SRE.

        Returns:
            True if confirmation succeeded, False if investigation not found.

        Raises:
            InvestigationServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/confirm",
                json={"comment": comment},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout confirming investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error confirming investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for confirmation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def reject_resolution(
        self,
        investigation_id: str,
        reason: str,
        reason_details: str | None = None,
        correction: str | None = None,
    ) -> bool:
        """Reject an investigation's resolution recommendation.

        Args:
            investigation_id: The investigation CRD name.
            reason: Rejection reason category.
            reason_details: Detailed explanation of rejection.
            correction: Optional corrective action suggested by SRE.

        Returns:
            True if rejection succeeded, False if investigation not found.

        Raises:
            InvestigationServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/reject",
                json={
                    "reason": reason,
                    "reason_details": reason_details,
                    "correction": correction,
                },
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout rejecting investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error rejecting investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for rejection %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def verify_investigation(self, investigation_id: str) -> bool:
        """Verify a resolved investigation (transition Resolved → Verified).

        Args:
            investigation_id: The investigation CRD name.

        Returns:
            True if verification succeeded, False if not found or invalid state.

        Raises:
            InvestigationServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/verify",
            )
            if response.status_code in (404, 409):
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout verifying investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error verifying investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for verification %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def resolve_investigation(
        self,
        investigation_id: str,
        outcome: str,
        accuracy_rating: str | None = None,
        resolution_notes: str | None = None,
        escalation_target: str | None = None,
        not_an_issue_reason: str | None = None,
    ) -> bool:
        """Resolve an investigation with a final outcome.

        Args:
            investigation_id: The investigation CRD name.
            outcome: Resolution outcome (resolved, not_an_issue, escalated, unresolved).
            accuracy_rating: Beeper accuracy rating (correct, partially_correct, incorrect).
            resolution_notes: Optional resolution notes.
            escalation_target: Escalation target (for escalated outcome).
            not_an_issue_reason: Reason for not-an-issue outcome.

        Returns:
            True if resolution succeeded, False if investigation not found.

        Raises:
            InvestigationServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/resolve",
                json={
                    "outcome": outcome,
                    "accuracy_rating": accuracy_rating,
                    "resolution_notes": resolution_notes,
                    "escalation_target": escalation_target,
                    "not_an_issue_reason": not_an_issue_reason,
                },
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout resolving investigation %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Timeout connecting to operator: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error resolving investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            raise InvestigationServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for resolution %s: %s",
                investigation_id, e,
            )
            raise InvestigationServiceError(
                f"Failed to connect to operator: {e}"
            ) from e

    def update_kb_with_resolution(
        self, investigation_id: str, resolution_data: dict[str, Any]
    ) -> bool:
        """Update KB knowledge entry with resolution data.

        Finds the KB entry linked to this investigation in the knowledge
        collection and adds resolution fields to its payload.

        Args:
            investigation_id: The investigation ID to look up in KB.
            resolution_data: Dict of resolution data to merge into KB entry.

        Returns:
            True if KB entry found and updated, False if no entry exists.
        """
        try:
            results, _ = self.qdrant_client.scroll(
                collection_name="knowledge",
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            if not results:
                logger.info(
                    "No KB entry found for investigation %s",
                    investigation_id,
                )
                return False
            point_id = results[0].id
            self.qdrant_client.set_payload(
                collection_name="knowledge",
                payload=resolution_data,
                points=[point_id],
            )
            return True
        except Exception as e:
            logger.warning(
                "Failed to update KB with resolution for %s: %s",
                investigation_id, e,
            )
            return False

    @staticmethod
    def calculate_mttr(
        started_at: str | None, resolved_at: str
    ) -> int | None:
        """Calculate MTTR (Mean Time To Resolution) in seconds.

        Args:
            started_at: ISO 8601 investigation start timestamp.
            resolved_at: ISO 8601 resolution timestamp.

        Returns:
            MTTR in seconds, or None if started_at is None.
        """
        if started_at is None:
            return None
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            return max(0, int((end - start).total_seconds()))
        except (ValueError, TypeError):
            return None

    def annotate_investigation(
        self, investigation_id: str, text: str, user: str
    ) -> bool:
        """Add an annotation to an active investigation.

        Args:
            investigation_id: The investigation CRD name.
            text: Annotation text from the user.
            user: The user adding the annotation.

        Returns:
            True if annotation succeeded, False on any error
            (not found, timeout, server error, connection error).
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/annotate",
                json={"text": text, "user": user},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout annotating investigation %s: %s",
                investigation_id, e,
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error annotating investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            return False
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for annotation %s: %s",
                investigation_id, e,
            )
            return False

    def redirect_investigation(
        self, investigation_id: str, instruction: str, user: str
    ) -> bool:
        """Redirect an active investigation with a new focus instruction.

        Args:
            investigation_id: The investigation CRD name.
            instruction: Redirect instruction from the user.
            user: The user issuing the redirect.

        Returns:
            True if redirect succeeded, False on any error
            (not found, timeout, server error, connection error).
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/redirect",
                json={"instruction": instruction, "user": user},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout redirecting investigation %s: %s",
                investigation_id, e,
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error redirecting investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            return False
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for redirect %s: %s",
                investigation_id, e,
            )
            return False

    def approve_fix(self, investigation_id: str, user: str) -> bool:
        """Approve a proposed fix for an investigation.

        Args:
            investigation_id: The investigation CRD name.
            user: The user approving the fix.

        Returns:
            True if approval succeeded, False on any error
            (not found, timeout, server error, connection error).
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/approve",
                json={"user": user},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout approving fix for investigation %s: %s",
                investigation_id, e,
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error approving fix for investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            return False
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for fix approval %s: %s",
                investigation_id, e,
            )
            return False

    def reject_fix(
        self, investigation_id: str, user: str, reason: str | None = None
    ) -> bool:
        """Reject a proposed fix for an investigation.

        Args:
            investigation_id: The investigation CRD name.
            user: The user rejecting the fix.
            reason: Optional reason for rejection.

        Returns:
            True if rejection succeeded, False on any error
            (not found, timeout, server error, connection error).
        """
        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/investigations/{investigation_id}/reject-fix",
                json={"user": user, "reason": reason},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout rejecting fix for investigation %s: %s",
                investigation_id, e,
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Operator returned error rejecting fix for investigation %s: %s",
                investigation_id, e.response.status_code,
            )
            return False
        except httpx.RequestError as e:
            logger.warning(
                "Failed to connect to operator for fix rejection %s: %s",
                investigation_id, e,
            )
            return False

    def save_resolution_feedback(
        self, investigation_id: str, feedback: dict[str, Any]
    ) -> None:
        """Save resolution feedback to Qdrant investigation metadata.

        Upserts feedback keys into the investigation's Qdrant payload
        alongside existing pipeline metadata.

        Args:
            investigation_id: The investigation ID.
            feedback: Dict of feedback data to merge into payload.
        """
        try:
            results, _ = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            if not results:
                logger.warning(
                    "No Qdrant record for investigation %s, skipping feedback",
                    investigation_id,
                )
                return
            point_id = results[0].id
            self.qdrant_client.set_payload(
                collection_name=INVESTIGATIONS_COLLECTION,
                payload=feedback,
                points=[point_id],
            )
        except Exception as e:
            logger.warning(
                "Failed to save resolution feedback for %s: %s",
                investigation_id, e,
            )


_REMEDIATION_STAGE_LABELS: dict[str, str] = {
    "proposed": "PR Open",
    "approved": "PR Approved",
    "testing": "Sandbox Testing",
    "applied": "Fix Applied",
    "verifying": "Verifying",
    "verified": "Verified",
    "rolled_back": "Rolled Back",
    "failed": "Failed",
}

_REMEDIATION_KEYS = {
    "runbook_found", "sandbox_executed", "verification_executed",
    "pr_generated", "trust_gate_evaluated", "kb_entry_created",
}


def compute_remediation_status(findings: dict[str, Any]) -> dict[str, Any] | None:
    """Compute remediation progress from Qdrant pipeline_metadata.

    Returns None if no remediation was attempted, or a dict with stage,
    label, stages_completed, pr_url, rollback_reason, verification_results.
    """
    if not findings or not _REMEDIATION_KEYS.intersection(findings):
        return None

    # Determine current stage (later stages override earlier ones)
    stage = "proposed"
    if findings.get("pr_generated"):
        stage = "proposed" if findings.get("draft") else "approved"
    if findings.get("sandbox_executed"):
        if findings.get("sandbox_overall_status") == "fail":
            stage = "failed"
        else:
            stage = "testing"
    if findings.get("trust_gate_evaluated"):
        stage = "applied"
    if findings.get("verification_executed"):
        v_status = findings.get("verification_status", "")
        if v_status == "confirmed":
            stage = "verified"
        elif v_status == "degraded":
            stage = "rolled_back"
        else:
            stage = "verifying"

    # Build completed stages list
    pipeline_stages = [
        ("proposed", findings.get("pr_generated") or findings.get("runbook_found")),
        ("approved", findings.get("pr_generated") and not findings.get("draft")),
        ("testing", findings.get("sandbox_executed")),
        ("applied", findings.get("trust_gate_evaluated")),
        ("verifying", findings.get("verification_executed")),
        ("verified", findings.get("verification_status") == "confirmed"),
    ]
    stages_completed = []
    for name, completed in pipeline_stages:
        status = "completed" if completed else "pending"
        stages_completed.append({"name": name, "status": status})

    # Rollback reason
    rollback_reason: str | None = None
    if stage == "rolled_back":
        rollback_paths = findings.get("trust_gate_rollback_paths", [])
        if rollback_paths and isinstance(rollback_paths, list):
            rollback_reason = rollback_paths[0].get("reason", "Metric degradation detected")
        else:
            rollback_reason = "Metric degradation detected"

    return {
        "stage": stage,
        "label": _REMEDIATION_STAGE_LABELS.get(stage, stage),
        "stages_completed": stages_completed,
        "pr_url": findings.get("pr_url"),
        "rollback_reason": rollback_reason,
        "verification_results": findings.get("verification_results"),
        "proven_fix_entry_id": findings.get("proven_fix_entry_id"),
    }


class InvestigationServiceError(Exception):
    """Error communicating with the investigation service."""

    pass
