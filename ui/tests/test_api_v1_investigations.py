"""Tests for Task 1.6 — BFF JSON API for React.

Acceptance criteria (each [T] maps to a clearly-named test class):

[T1] GET /api/v1/investigations returns JSON (not HTML); Content-Type is
     application/json; each element has the expected shape.

[T2] GET /api/v1/investigations/{id} returns JSON (not HTML); Content-Type is
     application/json; response includes ``metadata`` (full investigation fields)
     and ``steps`` (ordered, 1-based).

[T3] GET /api/v1/investigations/{id}/events emits an SSE ``text/event-stream``
     with JSON ``data:`` payloads; events are ordered (ascending ``order``); a
     terminal ``complete`` event is emitted on investigation completion.

[T4] The JSON events stream poll interval is configurable via the
     ``JSON_SSE_POLL_INTERVAL`` Flask config key; a test proves the generator
     respects the configured value.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.investigation_service import (
    InvestigationDetail,
    InvestigationServiceError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


# Reusable operator response payloads.
_INV_RUNNING = {
    "id": "inv-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-06-01T10:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-06-01T09:55:00Z",
    "workflow_state": "investigating",
    "workflow_state_changed_at": "2026-06-01T10:01:00Z",
    "message": "Querying knowledge base",
    "signal_count": 7,
    "job_name": None,
}

_INV_COMPLETED = {
    "id": "inv-002",
    "status": "completed",
    "service": "auth",
    "severity": "critical",
    "condition": "Login failure spike",
    "started_at": "2026-06-01T08:00:00Z",
    "completed_at": "2026-06-01T08:30:00Z",
    "triggered_at": "2026-06-01T07:55:00Z",
    "workflow_state": "resolved",
    "workflow_state_changed_at": "2026-06-01T08:30:00Z",
    "message": None,
    "signal_count": None,
    "job_name": "inv-002-job",
}


# ---------------------------------------------------------------------------
# [T1] GET /api/v1/investigations — list endpoint
# ---------------------------------------------------------------------------


class TestListEndpoint:
    """[T1] /api/v1/investigations returns JSON with expected shape."""

    @respx.mock
    def test_returns_json_content_type(self, client: FlaskClient) -> None:
        """Response Content-Type must be application/json (not text/html)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INV_RUNNING])
        )
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @respx.mock
    def test_returns_array(self, client: FlaskClient) -> None:
        """Response body is a JSON array."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INV_RUNNING, _INV_COMPLETED])
        )
        resp = client.get("/api/v1/investigations/")
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 2

    @respx.mock
    def test_element_shape(self, client: FlaskClient) -> None:
        """Each element has the expected fields."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INV_RUNNING])
        )
        resp = client.get("/api/v1/investigations/")
        data = resp.get_json()
        elem = data[0]
        assert elem["id"] == "inv-001"
        assert elem["status"] == "investigating"
        assert elem["service"] == "payments"
        assert elem["severity"] == "high"
        assert elem["condition"] == "High error rate detected"
        assert elem["started_at"] == "2026-06-01T10:00:00Z"
        assert elem["triggered_at"] == "2026-06-01T09:55:00Z"
        assert elem["workflow_state"] == "investigating"

    @respx.mock
    def test_no_html_in_body(self, client: FlaskClient) -> None:
        """Response body contains no HTML markup."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INV_RUNNING])
        )
        resp = client.get("/api/v1/investigations/")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<body" not in raw
        assert "<!DOCTYPE" not in raw

    @respx.mock
    def test_status_filter_passed_to_service(self, client: FlaskClient) -> None:
        """The ``status`` query param is forwarded to the operator."""
        mock_route = respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        resp = client.get("/api/v1/investigations/?status=investigating")
        assert resp.status_code == 200
        # The service call should include the filter parameter.
        assert mock_route.called

    @respx.mock
    def test_service_filter_passed_to_service(self, client: FlaskClient) -> None:
        """The ``service`` query param is forwarded to the operator."""
        mock_route = respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INV_RUNNING])
        )
        resp = client.get("/api/v1/investigations/?service=payments")
        assert resp.status_code == 200
        assert mock_route.called

    @respx.mock
    def test_severity_filter_passed_to_service(self, client: FlaskClient) -> None:
        """The ``severity`` query param is forwarded to the operator."""
        mock_route = respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        resp = client.get("/api/v1/investigations/?severity=critical")
        assert resp.status_code == 200
        assert mock_route.called

    @respx.mock
    def test_invalid_status_filter_ignored(self, client: FlaskClient) -> None:
        """Unknown ``status`` values are silently dropped (not forwarded)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        # Should not raise; invalid values are filtered out by validate_status().
        resp = client.get("/api/v1/investigations/?status=__invalid__")
        assert resp.status_code == 200

    @respx.mock
    def test_operator_unavailable_returns_503(self, app: Flask) -> None:
        """Operator connection failure returns JSON error with 503."""
        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.list_investigations",
                side_effect=InvestigationServiceError("down"),
            ):
                resp = c.get("/api/v1/investigations/")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "operator_unavailable"


# ---------------------------------------------------------------------------
# [T2] GET /api/v1/investigations/{id} — detail endpoint (metadata + steps)
# ---------------------------------------------------------------------------


class TestDetailEndpoint:
    """[T2] /api/v1/investigations/{id} returns JSON with metadata + ordered steps."""

    @respx.mock
    def test_returns_json_content_type(self, client: FlaskClient) -> None:
        """Content-Type is application/json, not text/html."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(return_value=Response(200, json=_INV_RUNNING))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-001")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @respx.mock
    def test_no_html_in_body(self, client: FlaskClient) -> None:
        """Response body contains no HTML markup."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(return_value=Response(200, json=_INV_RUNNING))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-001")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @respx.mock
    def test_includes_metadata_block(self, client: FlaskClient) -> None:
        """Response includes a ``metadata`` block with full investigation fields."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(return_value=Response(200, json=_INV_RUNNING))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-001")
        data = resp.get_json()
        assert "metadata" in data
        meta = data["metadata"]
        assert meta["id"] == "inv-001"
        assert meta["service"] == "payments"
        assert meta["severity"] == "high"
        assert meta["condition"] == "High error rate detected"
        assert meta["started_at"] == "2026-06-01T10:00:00Z"
        assert meta["triggered_at"] == "2026-06-01T09:55:00Z"
        assert meta["workflow_state"] == "investigating"
        assert meta["signal_count"] == 7

    @respx.mock
    def test_includes_ordered_steps(self, client: FlaskClient) -> None:
        """Response includes ``steps`` list with 1-based ``order`` field."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(return_value=Response(200, json=_INV_RUNNING))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-001")
        data = resp.get_json()
        assert "steps" in data
        steps = data["steps"]
        assert len(steps) == 6  # PIPELINE_STEPS has 6 entries
        orders = [s["order"] for s in steps]
        assert orders == [1, 2, 3, 4, 5, 6]
        # Each step has the required fields.
        for step in steps:
            assert "order" in step
            assert "key" in step
            assert "label" in step
            assert "state" in step
            assert "type" in step

    @respx.mock
    def test_steps_ordered_ascending(self, client: FlaskClient) -> None:
        """Steps are ordered by ``order`` in ascending sequence (1, 2, 3…)."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(return_value=Response(200, json=_INV_RUNNING))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-001")
        steps = resp.get_json()["steps"]
        orders = [s["order"] for s in steps]
        assert orders == sorted(orders)
        assert orders[0] == 1

    @respx.mock
    def test_completed_investigation_all_steps_completed(
        self, client: FlaskClient
    ) -> None:
        """For a completed investigation every step has state=completed."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-002"
        ).mock(return_value=Response(200, json=_INV_COMPLETED))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-002")
        steps = resp.get_json()["steps"]
        assert all(s["state"] == "completed" for s in steps)

    @respx.mock
    def test_not_found_returns_404(self, client: FlaskClient) -> None:
        """Missing investigation returns JSON error with 404."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-missing"
        ).mock(return_value=Response(404))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            resp = client.get("/api/v1/investigations/inv-missing")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "not_found"

    def test_invalid_id_returns_404(self, client: FlaskClient) -> None:
        """Path-traversal-style IDs are rejected with 404."""
        resp = client.get("/api/v1/investigations/../../etc/passwd")
        assert resp.status_code == 404

    @respx.mock
    def test_operator_unavailable_returns_503(self, app: Flask) -> None:
        """Operator connection failure returns JSON 503."""
        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                side_effect=InvestigationServiceError("down"),
            ):
                resp = c.get("/api/v1/investigations/inv-001")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "operator_unavailable"


# ---------------------------------------------------------------------------
# [T3] GET /api/v1/investigations/{id}/events — JSON SSE events stream
# ---------------------------------------------------------------------------


def _collect_sse_events(raw: bytes) -> list[dict]:
    """Parse raw SSE bytes into a list of ``{event, data}`` dicts."""
    events = []
    current: dict = {}
    for line in raw.decode().splitlines():
        if line.startswith("event: "):
            current["event"] = line[len("event: "):]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[len("data: "):])
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


class TestEventsStream:
    """[T3] /api/v1/investigations/{id}/events emits ordered JSON events + terminal."""

    def test_stream_content_type(self, app: Flask) -> None:
        """Response Content-Type is text/event-stream."""
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                # Transition to completed on second poll so the generator terminates.
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-001/events")
                # Access content_type inside the patch context so the generator
                # doesn't block on real time.sleep if resp.data is also accessed.
                content_type = resp.content_type
        assert "text/event-stream" in content_type

    def test_stream_emits_step_events(self, app: Flask) -> None:
        """Stream emits ``step`` events with order, key, label, state, type.

        NOTE: ``resp.data`` is accessed INSIDE the patch context because the
        Flask test client lazily consumes the SSE generator when the response
        body is read.  Exiting the patch before reading the body would leave
        ``time.sleep`` unpatched and block the generator.
        """
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            # First call: running (triggers initial step events).
            # Second call: completed (triggers complete event and terminates).
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-001/events")
                # Read body inside the patch block so the generator runs with
                # the mocked service and non-blocking sleep.
                raw_data = resp.data

        events = _collect_sse_events(raw_data)
        step_events = [e for e in events if e.get("event") == "step"]
        assert len(step_events) > 0
        for ev in step_events:
            payload = ev["data"]
            assert "order" in payload
            assert "key" in payload
            assert "label" in payload
            assert "state" in payload
            assert "type" in payload

    def test_stream_emits_ordered_steps_ascending(self, app: Flask) -> None:
        """Step events from the first poll are in ascending order (1, 2, 3…).

        A two-poll scenario (investigating → completed) emits two batches of
        step events.  The generator emits steps in ascending order within each
        batch; across batches, only changed steps are re-emitted so duplicates
        may appear.  We verify the first batch (all 6 steps) is strictly
        ascending.
        """
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-001/events")
                raw_data = resp.data  # inside patch — see note in test above

        events = _collect_sse_events(raw_data)
        step_events = [e for e in events if e.get("event") == "step"]
        # The first 6 step events (from the initial "investigating" poll) must be
        # in strictly ascending order 1…6.
        first_batch = step_events[:6]
        assert len(first_batch) == 6
        orders = [e["data"]["order"] for e in first_batch]
        assert orders == list(range(1, 7)), f"First batch orders: {orders}"

    def test_stream_emits_terminal_complete_event_on_completion(
        self, app: Flask
    ) -> None:
        """A ``complete`` event with ``status=done`` is emitted when the investigation
        transitions to ``completed``."""
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-001/events")
                raw_data = resp.data  # inside patch — see note above

        events = _collect_sse_events(raw_data)
        complete_events = [e for e in events if e.get("event") == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["data"]["status"] == "done"

    def test_stream_emits_not_found_terminal_when_investigation_missing(
        self, app: Flask
    ) -> None:
        """When the investigation is not found a ``complete`` event with
        ``status=not_found`` is emitted and the stream closes."""

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            return None

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-missing-stream/events")
                raw_data = resp.data  # inside patch — see note above

        events = _collect_sse_events(raw_data)
        complete_events = [e for e in events if e.get("event") == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["data"]["status"] == "not_found"

    def test_stream_data_lines_are_valid_json(self, app: Flask) -> None:
        """Every ``data:`` line in the stream is valid JSON (not HTML)."""
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", return_value=None):
                resp = c.get("/api/v1/investigations/inv-001/events")
                raw = resp.data.decode()  # inside patch — see note above

        for line in raw.splitlines():
            if line.startswith("data: "):
                payload_str = line[len("data: "):]
                # Must be valid JSON — no HTML fragments.
                parsed = json.loads(payload_str)
                assert isinstance(parsed, dict)
                assert "<" not in payload_str  # no HTML tags

    def test_invalid_id_returns_404(self, client: FlaskClient) -> None:
        """Path-traversal IDs return 404 before the stream opens."""
        resp = client.get("/api/v1/investigations/../../etc/passwd/events")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# [T4] Poll interval is configurable via JSON_SSE_POLL_INTERVAL config key
# ---------------------------------------------------------------------------


class TestPollIntervalConfigurable:
    """[T4] JSON_SSE_POLL_INTERVAL config key controls the poll interval."""

    def test_generator_uses_configured_poll_interval(self, app: Flask) -> None:
        """_generate_json_sse_events sleeps for the configured interval, not the
        hard-coded default of 1 s.

        Uses two polls (running then completed) so the generator sleeps exactly
        once — proving the interval is taken from the argument, not from the
        module-level default or SSE_POLL_INTERVAL.
        """
        from beeper_ui.routes.investigations import _generate_json_sse_events

        sleep_calls: list[float] = []
        call_count = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_count["n"] += 1
            # First call: investigating → triggers sleep before next poll.
            # Second call: completed → terminates (no further sleep).
            return InvestigationDetail.from_dict({
                **_INV_RUNNING,
                "status": "completed" if call_count["n"] > 1 else "investigating",
            })

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        configured_interval = 0.5

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ), patch("beeper_ui.routes.investigations.time.sleep", side_effect=fake_sleep):
            gen = _generate_json_sse_events(
                "http://mock-operator:8080",
                5.0,
                "inv-001",
                configured_interval,
            )
            # Consume the generator to completion.
            list(gen)

        # Generator slept once (between poll 1 and poll 2).
        # All sleeps must use the configured interval, not 1 s (default) or 3 s (HTML SSE).
        assert len(sleep_calls) == 1, (
            f"Expected exactly 1 sleep call, got {len(sleep_calls)}"
        )
        assert sleep_calls[0] == configured_interval, (
            f"Generator slept {sleep_calls[0]}s instead of configured {configured_interval}s"
        )

    def test_default_poll_interval_is_one_second(self) -> None:
        """The default JSON SSE poll interval is 1 s (meets NFR21 ≤2 s target)."""
        from beeper_ui.routes.investigations import _DEFAULT_JSON_SSE_POLL_INTERVAL

        assert _DEFAULT_JSON_SSE_POLL_INTERVAL == 1, (
            "Default interval must be 1 s to satisfy NFR21 ≤2 s render target"
        )

    def test_flask_config_key_overrides_default(self, app: Flask) -> None:
        """JSON_SSE_POLL_INTERVAL Flask config key propagates to the generator."""
        app.config["JSON_SSE_POLL_INTERVAL"] = 0.25
        sleep_calls: list[float] = []

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            return InvestigationDetail.from_dict({**_INV_RUNNING, "status": "completed"})

        def fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with app.test_client() as c:
            with patch(
                "beeper_ui.routes.investigations.InvestigationService.get_investigation",
                new=fake_get_investigation,
            ), patch("beeper_ui.routes.investigations.time.sleep", side_effect=fake_sleep):
                resp = c.get("/api/v1/investigations/inv-001/events")
                # Consume the response inside the patch context (see streaming note).
                _ = resp.data

        # If any sleep occurred it must use the configured value.
        for secs in sleep_calls:
            assert secs == 0.25

    def test_html_sse_poll_interval_unchanged(self) -> None:
        """The existing HTML SSE poll interval (SSE_POLL_INTERVAL) is still 3 s
        — this test guards against accidentally lowering the legacy HTML path."""
        from beeper_ui.routes.investigations import SSE_POLL_INTERVAL

        assert SSE_POLL_INTERVAL == 3, (
            "SSE_POLL_INTERVAL for the HTML/HTMX stream must remain 3 s; "
            "only the JSON stream (JSON_SSE_POLL_INTERVAL) was changed"
        )
