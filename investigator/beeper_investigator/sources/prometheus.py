"""Prometheus HTTP API client for the investigator agent.

Provides PromQL query and range_query methods using httpx.
"""

import base64
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class PrometheusClient:
    """HTTP client for the Prometheus query API.

    Args:
        base_url: Prometheus server URL (e.g. ``http://prometheus:9090``).
            Defaults to the ``PROMETHEUS_URL`` env var.
        auth: Base64-encoded ``user:pass`` for basic auth.
            Defaults to the ``PROMETHEUS_AUTH`` env var.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("PROMETHEUS_URL", "")).rstrip("/")
        auth_b64 = auth or os.environ.get("PROMETHEUS_AUTH", "")

        headers: dict[str, str] = {}
        if auth_b64:
            try:
                # Validate the value is valid base64 containing "user:pass"
                decoded = base64.b64decode(auth_b64).decode()
                if ":" not in decoded:
                    raise ValueError("Expected 'user:pass' format")
                headers["Authorization"] = f"Basic {auth_b64}"
            except Exception:
                logger.warning("Invalid PROMETHEUS_AUTH value, ignoring")

        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout)

    def query(self, promql: str, time: Optional[str] = None) -> dict[str, Any]:
        """Execute an instant PromQL query.

        Args:
            promql: PromQL expression.
            time: Evaluation timestamp (RFC3339 or Unix). Omit for *now*.

        Returns:
            Prometheus API response ``data`` object.
        """
        params: dict[str, str] = {"query": promql}
        if time:
            params["time"] = time

        resp = self._client.get("/api/v1/query", params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        data: dict[str, Any] = body.get("data", {})
        return data

    def query_range(
        self, promql: str, start: str, end: str, step: str = "60s"
    ) -> dict[str, Any]:
        """Execute a range PromQL query.

        Args:
            promql: PromQL expression.
            start: Start timestamp (RFC3339 or Unix).
            end: End timestamp (RFC3339 or Unix).
            step: Query resolution step (e.g. ``60s``).

        Returns:
            Prometheus API response ``data`` object.
        """
        params = {"query": promql, "start": start, "end": end, "step": step}
        resp = self._client.get("/api/v1/query_range", params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        data: dict[str, Any] = body.get("data", {})
        return data

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
