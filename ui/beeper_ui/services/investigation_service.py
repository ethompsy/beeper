"""Investigation service for fetching investigation status from the operator."""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None

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


class InvestigationServiceError(Exception):
    """Error communicating with the investigation service."""

    pass
