"""Source service for fetching source status from the operator."""

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SourceError:
    """Error details for a source."""

    type: str
    message: str
    details: str | None = None


@dataclass
class Source:
    """A configured data source."""

    name: str
    type: str
    endpoint: str
    status: str
    last_check: str | None = None
    error: SourceError | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        """Create Source from dictionary."""
        error = None
        if data.get("error"):
            error = SourceError(
                type=data["error"].get("type", "unknown"),
                message=data["error"].get("message", "Unknown error"),
                details=data["error"].get("details"),
            )
        return cls(
            name=data["name"],
            type=data["type"],
            endpoint=data["endpoint"],
            status=data["status"],
            last_check=data.get("last_check"),
            error=error,
        )


class SourceService:
    """Service for fetching source status from the operator API."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        """Initialize the source service.

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

    def get_sources(self) -> list[Source]:
        """Fetch all configured sources from the operator.

        Returns:
            List of Source objects.

        Raises:
            SourceServiceError: If the operator cannot be reached or returns an error.
        """
        try:
            response = self.client.get(f"{self.operator_url}/api/v1/sources")
            response.raise_for_status()
            data = response.json()
            # De-duplicate by source name so an operator restart that briefly
            # re-reports the same Source CRD during reconciliation never
            # surfaces doubled rows in the UI (NFR12 consistency property).
            # Last occurrence wins, preserving the freshest status snapshot.
            deduped: dict[str, Source] = {}
            for raw in data.get("sources", []):
                source = Source.from_dict(raw)
                deduped[source.name] = source
            # Sort alphabetically by name
            return sorted(deduped.values(), key=lambda s: s.name)
        except httpx.TimeoutException as e:
            raise SourceServiceError(f"Timeout connecting to operator: {e}") from e
        except httpx.HTTPStatusError as e:
            raise SourceServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise SourceServiceError(f"Failed to connect to operator: {e}") from e


class SourceServiceError(Exception):
    """Error communicating with the source service."""

    pass
