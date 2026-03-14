"""SLO service for fetching SLO compliance data from the operator API."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SloServiceError(Exception):
    """Error communicating with the SLO service."""

    pass


class SloService:
    """Service for fetching SLO data from the operator API."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        """Initialize the SLO service.

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

    def get_services(self) -> list[dict[str, Any]]:
        """Fetch all services with SLO status.

        Returns:
            List of service level dicts.

        Raises:
            SloServiceError: If the operator cannot be reached.
        """
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/slo/services"
            )
            response.raise_for_status()
            result: list[dict[str, Any]] = response.json().get("service_levels", [])
            return result
        except httpx.TimeoutException as e:
            raise SloServiceError(f"Timeout connecting to operator: {e}") from e
        except httpx.HTTPStatusError as e:
            raise SloServiceError(
                f"Operator returned error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise SloServiceError(f"Failed to connect to operator: {e}") from e

    def get_service_detail(self, name: str) -> dict[str, Any] | None:
        """Fetch SLO detail for a specific service.

        Args:
            name: ServiceLevel CRD name.

        Returns:
            Service detail dict, or None if not found.
        """
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/slo/services/{name}"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            detail: dict[str, Any] = response.json()
            return detail
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.exception("Failed to fetch SLO detail for %s: %s", name, e)
            return None

    def get_service_budget(self, name: str) -> dict[str, Any] | None:
        """Fetch error budget status for a specific service.

        Args:
            name: ServiceLevel CRD name.

        Returns:
            Error budget dict, or None if not found.
        """
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/slo/services/{name}/budget"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            budget: dict[str, Any] = response.json()
            return budget
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.exception(
                "Failed to fetch error budget for %s: %s", name, e
            )
            return None


def format_compliance(value: float | None) -> str:
    """Format compliance as percentage.

    Args:
        value: Compliance value (0.0-1.0), or None.

    Returns:
        Formatted string like "99.90%" or "N/A".
    """
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_burn_rate(value: float | None) -> str:
    """Format burn rate with multiplier notation.

    Args:
        value: Burn rate multiplier, or None.

    Returns:
        Formatted string like "5.2x" or "N/A".
    """
    if value is None:
        return "N/A"
    return f"{value:.1f}x"


def format_percentage(value: float | None) -> str:
    """Format a fraction (0.0-1.0) as percentage.

    Args:
        value: Fraction value, or None.

    Returns:
        Formatted string like "75.0%" or "N/A".
    """
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def format_budget_remaining(value: float | None) -> str:
    """Format error budget remaining as percentage.

    Args:
        value: Budget remaining (0.0-1.0), or None.

    Returns:
        Formatted string like "75.0%" or "N/A".
    """
    return format_percentage(value)


def format_projected_exhaustion(secs: float | None) -> str:
    """Convert seconds to human-readable duration.

    Args:
        secs: Seconds until exhaustion, or None.

    Returns:
        Formatted string like "3d 4h", "2h 30m", "45m", or "N/A".
    """
    if secs is None or secs <= 0:
        return "N/A"
    days = int(secs // 86400)
    hours = int((secs % 86400) // 3600)
    minutes = int((secs % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m"
    seconds = int(secs)
    return f"{seconds}s"


def condition_css_class(condition: str) -> str:
    """Map SLO condition to CSS class.

    Args:
        condition: One of "healthy", "warning", "critical", "unknown".

    Returns:
        CSS class string.
    """
    mapping = {
        "healthy": "status-healthy",
        "warning": "status-warning",
        "critical": "status-critical",
    }
    return mapping.get(condition, "status-neutral")
