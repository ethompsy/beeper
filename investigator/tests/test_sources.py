"""Tests for source query clients (Prometheus, Loki)."""

import base64
import os
from unittest.mock import patch

import httpx
import pytest

from beeper_investigator.sources.prometheus import PrometheusClient
from beeper_investigator.sources.loki import LokiClient


# ── Prometheus ──────────────────────────────────────────────


class TestPrometheusClient:
    """Tests for PrometheusClient."""

    def test_query_sends_promql(self) -> None:
        """query() sends the PromQL expression to the correct endpoint."""
        response_data = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "42"]}]},
        }
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=response_data)
        )
        client = PrometheusClient.__new__(PrometheusClient)
        client.base_url = "http://prometheus:9090"
        client._client = httpx.Client(
            base_url="http://prometheus:9090", transport=transport
        )

        result = client.query('up{job="api"}')

        assert result["resultType"] == "vector"
        assert len(result["result"]) == 1

    def test_query_range_sends_parameters(self) -> None:
        """query_range() sends start, end, step parameters."""
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "matrix", "result": []}},
            )

        transport = httpx.MockTransport(handler)
        client = PrometheusClient.__new__(PrometheusClient)
        client.base_url = "http://prometheus:9090"
        client._client = httpx.Client(
            base_url="http://prometheus:9090", transport=transport
        )

        client.query_range("rate(http_requests_total[5m])", "1000", "2000", "30s")

        assert "start=1000" in captured["url"]
        assert "end=2000" in captured["url"]
        assert "step=30s" in captured["url"]

    def test_connection_failure_raises(self) -> None:
        """Connection failure raises httpx.ConnectError."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        client = PrometheusClient.__new__(PrometheusClient)
        client.base_url = "http://prometheus:9090"
        client._client = httpx.Client(
            base_url="http://prometheus:9090", transport=transport
        )

        with pytest.raises(httpx.ConnectError):
            client.query("up")

    def test_reads_url_from_env(self) -> None:
        """PrometheusClient reads PROMETHEUS_URL from env."""
        with patch.dict(os.environ, {"PROMETHEUS_URL": "http://prom:9090"}, clear=False):
            client = PrometheusClient()
            assert client.base_url == "http://prom:9090"
            client.close()

    def test_basic_auth_sets_header(self) -> None:
        """Basic auth env var sets Authorization header on requests."""
        auth_b64 = base64.b64encode(b"admin:secret").decode()
        captured_headers: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(req.headers)
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "vector", "result": []}},
            )

        with patch.dict(os.environ, {
            "PROMETHEUS_URL": "http://prom:9090",
            "PROMETHEUS_AUTH": auth_b64,
        }, clear=False):
            client = PrometheusClient()
            # Replace transport with mock
            client._client = httpx.Client(
                base_url=client.base_url,
                headers=client._client.headers,
                transport=httpx.MockTransport(handler),
            )
            client.query("up")

        assert "authorization" in captured_headers
        assert captured_headers["authorization"] == f"Basic {auth_b64}"
        client.close()

    def test_invalid_auth_ignored(self) -> None:
        """Invalid PROMETHEUS_AUTH value is ignored (no crash, no header)."""
        with patch.dict(os.environ, {
            "PROMETHEUS_URL": "http://prom:9090",
            "PROMETHEUS_AUTH": "not-valid-base64!!!",
        }, clear=False):
            client = PrometheusClient()
            # Should not have Authorization header
            assert "authorization" not in {
                k.lower() for k in client._client.headers.keys()
            }
            client.close()


# ── Loki ────────────────────────────────────────────────────


class TestLokiClient:
    """Tests for LokiClient."""

    def test_query_sends_logql(self) -> None:
        """query() sends the LogQL expression to the correct endpoint."""
        response_data = {
            "status": "success",
            "data": {"resultType": "streams", "result": [{"stream": {}, "values": []}]},
        }
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            return httpx.Response(200, json=response_data)

        transport = httpx.MockTransport(handler)
        client = LokiClient.__new__(LokiClient)
        client.base_url = "http://loki:3100"
        client._client = httpx.Client(
            base_url="http://loki:3100", transport=transport
        )

        result = client.query('{job="api"} |= "error"')

        assert result["resultType"] == "streams"
        assert "query=" in captured["url"]

    def test_query_range_sends_parameters(self) -> None:
        """query_range() sends start, end, limit parameters."""
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "streams", "result": []}},
            )

        transport = httpx.MockTransport(handler)
        client = LokiClient.__new__(LokiClient)
        client.base_url = "http://loki:3100"
        client._client = httpx.Client(
            base_url="http://loki:3100", transport=transport
        )

        client.query_range('{job="api"}', "1000000000000", "2000000000000", limit=500)

        assert "start=1000000000000" in captured["url"]
        assert "end=2000000000000" in captured["url"]
        assert "limit=500" in captured["url"]

    def test_connection_failure_raises(self) -> None:
        """Connection failure raises httpx.ConnectError."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        client = LokiClient.__new__(LokiClient)
        client.base_url = "http://loki:3100"
        client._client = httpx.Client(
            base_url="http://loki:3100", transport=transport
        )

        with pytest.raises(httpx.ConnectError):
            client.query('{job="api"}')

    def test_reads_url_from_env(self) -> None:
        """LokiClient reads LOKI_URL from env."""
        with patch.dict(os.environ, {"LOKI_URL": "http://loki:3100"}, clear=False):
            client = LokiClient()
            assert client.base_url == "http://loki:3100"
            client.close()

    def test_basic_auth_sets_header(self) -> None:
        """Basic auth env var sets Authorization header on requests."""
        auth_b64 = base64.b64encode(b"user:pass123").decode()
        captured_headers: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(req.headers)
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "streams", "result": []}},
            )

        with patch.dict(os.environ, {
            "LOKI_URL": "http://loki:3100",
            "LOKI_AUTH": auth_b64,
        }, clear=False):
            client = LokiClient()
            client._client = httpx.Client(
                base_url=client.base_url,
                headers=client._client.headers,
                transport=httpx.MockTransport(handler),
            )
            client.query('{job="api"}')

        assert "authorization" in captured_headers
        assert captured_headers["authorization"] == f"Basic {auth_b64}"
        client.close()

    def test_invalid_auth_ignored(self) -> None:
        """Invalid LOKI_AUTH value is ignored (no crash, no header)."""
        with patch.dict(os.environ, {
            "LOKI_URL": "http://loki:3100",
            "LOKI_AUTH": "not-valid-base64!!!",
        }, clear=False):
            client = LokiClient()
            assert "authorization" not in {
                k.lower() for k in client._client.headers.keys()
            }
            client.close()
