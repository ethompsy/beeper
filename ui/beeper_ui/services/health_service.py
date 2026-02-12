"""Health service for fetching operator health status."""

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ComponentStatus:
    """Health status of a single component."""

    status: str
    message: str


@dataclass
class HealthStatus:
    """Overall health status of the operator."""

    overall: str
    components: dict[str, ComponentStatus]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HealthStatus":
        """Create HealthStatus from dictionary."""
        components = {}
        for name, comp in data.get("components", {}).items():
            components[name] = ComponentStatus(
                status=comp.get("status", "unknown"),
                message=comp.get("message", ""),
            )
        return cls(
            overall=data.get("overall", "unknown"),
            components=components,
        )


@dataclass
class IngestionStats:
    """Ingestion buffer statistics."""

    buffer_size: int
    buffered_count: int
    dropped_count: int
    is_full: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionStats":
        """Create IngestionStats from dictionary."""
        return cls(
            buffer_size=data.get("buffer_size", 0),
            buffered_count=data.get("buffered_count", 0),
            dropped_count=data.get("dropped_count", 0),
            is_full=data.get("is_full", False),
        )


class HealthService:
    """Service for fetching operator health status."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        """Initialize the health service.

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

    def get_health(self) -> HealthStatus:
        """Fetch health status from the operator.

        Returns:
            HealthStatus object with component statuses.

        Raises:
            HealthServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.get(f"{self.operator_url}/api/v1/health/components")
            response.raise_for_status()
            return HealthStatus.from_dict(response.json())
        except httpx.TimeoutException as e:
            raise HealthServiceError(f"Timeout connecting to operator: {e}") from e
        except httpx.HTTPStatusError as e:
            raise HealthServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise HealthServiceError(f"Failed to connect to operator: {e}") from e

    def get_ingestion_stats(self) -> IngestionStats:
        """Fetch ingestion buffer statistics.

        Returns:
            IngestionStats object.

        Raises:
            HealthServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.get(f"{self.operator_url}/api/v1/ingestion/stats")
            response.raise_for_status()
            return IngestionStats.from_dict(response.json())
        except httpx.TimeoutException as e:
            raise HealthServiceError(f"Timeout connecting to operator: {e}") from e
        except httpx.HTTPStatusError as e:
            raise HealthServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise HealthServiceError(f"Failed to connect to operator: {e}") from e

    def is_operator_healthy(self) -> bool:
        """Check if the operator basic health check passes.

        Returns:
            True if operator is healthy, False otherwise.
        """
        try:
            response = self.client.get(f"{self.operator_url}/healthz")
            return response.status_code == 200
        except httpx.RequestError:
            return False


class HealthServiceError(Exception):
    """Error communicating with the health service."""

    pass
