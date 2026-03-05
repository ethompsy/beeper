"""Loki HTTP API client for the investigator agent.

Provides LogQL query and range_query methods using httpx.
"""

import base64
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class LokiClient:
    """HTTP client for the Loki query API.

    Args:
        base_url: Loki server URL (e.g. ``http://loki:3100``).
            Defaults to the ``LOKI_URL`` env var.
        auth: Base64-encoded ``user:pass`` for basic auth.
            Defaults to the ``LOKI_AUTH`` env var.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LOKI_URL", "")).rstrip("/")
        auth_b64 = auth or os.environ.get("LOKI_AUTH", "")

        headers: dict[str, str] = {}
        if auth_b64:
            try:
                # Validate the value is valid base64 containing "user:pass"
                decoded = base64.b64decode(auth_b64).decode()
                if ":" not in decoded:
                    raise ValueError("Expected 'user:pass' format")
                headers["Authorization"] = f"Basic {auth_b64}"
            except Exception:
                logger.warning("Invalid LOKI_AUTH value, ignoring")

        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout)

    def query(
        self, logql: str, limit: int = 100, time: Optional[str] = None
    ) -> dict[str, Any]:
        """Execute an instant LogQL query.

        Args:
            logql: LogQL expression.
            limit: Maximum number of entries to return.
            time: Evaluation timestamp (RFC3339 or Unix). Omit for *now*.

        Returns:
            Loki API response ``data`` object.
        """
        params: dict[str, str] = {"query": logql, "limit": str(limit)}
        if time:
            params["time"] = time

        resp = self._client.get("/loki/api/v1/query", params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        data: dict[str, Any] = body.get("data", {})
        return data

    def query_range(
        self,
        logql: str,
        start: str,
        end: str,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Execute a range LogQL query.

        Args:
            logql: LogQL expression.
            start: Start timestamp (nanosecond Unix epoch string).
            end: End timestamp (nanosecond Unix epoch string).
            limit: Maximum number of entries to return.

        Returns:
            Loki API response ``data`` object.
        """
        params = {"query": logql, "start": start, "end": end, "limit": str(limit)}
        resp = self._client.get("/loki/api/v1/query_range", params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        data: dict[str, Any] = body.get("data", {})
        return data

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
