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
    """Ingestion + detection pipeline statistics.

    Buffer fields existed before Task 1.4. The pipeline-diagnostic fields
    (metrics/logs received, anomaly detection counters, and the EWMA warmup
    progress) were added to ``GET /api/v1/ingestion/stats`` by Task 1.4 and
    are surfaced on the Observe > Ingestion Stats dashboard (Task 5.2, FR32-33).
    All fields are snake_case to match the operator JSON exactly.
    """

    buffer_size: int
    buffered_count: int
    dropped_count: int
    is_full: bool
    # Task 1.4 pipeline-diagnostic fields (FR32-33).
    metrics_received: int
    logs_received: int
    anomalies_detected: int
    anomalies_suppressed: int
    active_metric_detectors: int
    ewma_warmup_samples: int
    ewma_warmup_minimum: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionStats":
        """Create IngestionStats from dictionary."""
        return cls(
            buffer_size=data.get("buffer_size", 0),
            buffered_count=data.get("buffered_count", 0),
            dropped_count=data.get("dropped_count", 0),
            is_full=data.get("is_full", False),
            metrics_received=data.get("metrics_received", 0),
            logs_received=data.get("logs_received", 0),
            anomalies_detected=data.get("anomalies_detected", 0),
            anomalies_suppressed=data.get("anomalies_suppressed", 0),
            active_metric_detectors=data.get("active_metric_detectors", 0),
            ewma_warmup_samples=data.get("ewma_warmup_samples", 0),
            ewma_warmup_minimum=data.get("ewma_warmup_minimum", 0),
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
