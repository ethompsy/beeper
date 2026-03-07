"""Investigation service for fetching investigation status from the operator."""

import logging
import os
from dataclasses import dataclass
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
        )


@dataclass
class InvestigationDetail(Investigation):
    """Extended investigation with detail fields."""

    message: str | None = None
    error: str | None = None
    job_name: str | None = None

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


class InvestigationServiceError(Exception):
    """Error communicating with the investigation service."""

    pass
