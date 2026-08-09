"""Tests for the JSON SSE keepalive re-auth hook (Task 8.3 — ADR 0002 §2/
NFR25): `_build_sse_reauth_check()` and `_generate_json_sse_events()`'s
`reauth_check` parameter in `beeper_ui.routes.investigations`.

Unit-level with the generator directly (no cluster, no real SSE client) —
mirrors the existing `TestPollIntervalConfigurable` pattern in
`tests/test_api_v1_investigations.py`.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from flask import Flask, session

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    reset_identity_store,
    set_identity_store_for_testing,
)
from beeper_ui.services.investigation_service import InvestigationDetail
from tests._fake_qdrant import FakeQdrantClient

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


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-sse-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


class _LocalConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"


class _OidcNoScimConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = False


@pytest.fixture
def fake_client() -> FakeQdrantClient:
    return FakeQdrantClient()


@pytest.fixture
def seeded_store(
    fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
) -> IdentityStoreService:
    monkeypatch.setattr(
        "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
    )
    store = IdentityStoreService(admin_groups=("Admins", "beeper-admin"))
    set_identity_store_for_testing(store)
    return store


def _set_raw_session_identity(
    *,
    sub: str,
    role_snapshot: str = "user",
    exp_offset: float = 8 * 3600,
) -> None:
    now = time.time()
    session["identity"] = {
        "sub": sub,
        "email": None,
        "email_lc": None,
        "external_id": None,
        "name": None,
        "role_snapshot": role_snapshot,
        "iat": now,
        "exp": now + exp_offset,
    }


# ---------------------------------------------------------------------------
# [T] `_generate_json_sse_events(..., reauth_check=...)`
# ---------------------------------------------------------------------------


class TestGeneratorReauthCheck:
    @pytest.fixture
    def app(self) -> Flask:
        return create_app(TestingConfig)

    def test_reauth_check_none_matches_pre_8_3_behavior(self, app: Flask) -> None:
        """Default (`reauth_check=None`, and always the case in mode
        `none`) — the stream completes exactly as before Task 8.3."""
        from beeper_ui.routes.investigations import _generate_json_sse_events

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            return InvestigationDetail.from_dict({**_INV_RUNNING, "status": "completed"})

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ):
            events = list(
                _generate_json_sse_events("http://mock-operator:8080", 5.0, "inv-001", 1.0)
            )
        assert any("event: complete" in e for e in events)
        assert any('"status": "done"' in e for e in events)

    def test_terminates_immediately_when_reauth_fails_on_first_tick(
        self, app: Flask
    ) -> None:
        """Never-authorized case: the stream ends WITHOUT ever polling the
        operator or emitting any event."""
        from beeper_ui.routes.investigations import _generate_json_sse_events

        poll_calls = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            poll_calls["n"] += 1
            return InvestigationDetail.from_dict(_INV_RUNNING)

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ):
            events = list(
                _generate_json_sse_events(
                    "http://mock-operator:8080",
                    5.0,
                    "inv-001",
                    1.0,
                    reauth_check=lambda: False,
                )
            )
        assert events == []
        assert poll_calls["n"] == 0

    def test_continues_normally_when_reauth_always_succeeds(self, app: Flask) -> None:
        from beeper_ui.routes.investigations import _generate_json_sse_events

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            return InvestigationDetail.from_dict({**_INV_RUNNING, "status": "completed"})

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ):
            events = list(
                _generate_json_sse_events(
                    "http://mock-operator:8080",
                    5.0,
                    "inv-001",
                    1.0,
                    reauth_check=lambda: True,
                )
            )
        assert any("event: complete" in e for e in events)

    def test_terminates_at_next_poll_tick_after_mid_stream_deactivation(
        self, app: Flask
    ) -> None:
        """[T] The named AC: a stream whose identity is deactivated
        mid-stream terminates at the NEXT poll tick — proven by an
        operator fake that never completes (always "investigating") so the
        ONLY possible termination cause is the re-auth check going false."""
        from beeper_ui.routes.investigations import _generate_json_sse_events

        reauth_state = {"calls": 0}

        def reauth_check() -> bool:
            reauth_state["calls"] += 1
            # Authorized for the first 2 poll ticks, "deactivated" from the
            # 3rd tick onward.
            return reauth_state["calls"] <= 2

        poll_calls = {"n": 0}

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            poll_calls["n"] += 1
            return InvestigationDetail.from_dict({**_INV_RUNNING, "status": "investigating"})

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ), patch("beeper_ui.routes.investigations.time.sleep"):
            events = list(
                _generate_json_sse_events(
                    "http://mock-operator:8080",
                    5.0,
                    "inv-001",
                    1.0,
                    reauth_check=reauth_check,
                )
            )

        # Checked once per tick: tick 1 (ok, poll), tick 2 (ok, poll), tick 3
        # (fails — terminate BEFORE polling again).
        assert reauth_state["calls"] == 3
        assert poll_calls["n"] == 2
        # No terminal "complete" event — the stream simply stops; the
        # client's reconnect-on-error path converts this into the normal
        # 401 -> login flow (ADR §2).
        assert not any("event: complete" in e for e in events)

    def test_reauth_check_runs_before_polling_each_tick(self, app: Flask) -> None:
        """Ordering guarantee: re-auth is checked BEFORE the operator poll,
        so an already-deactivated identity never leaks even one more poll's
        data."""
        from beeper_ui.routes.investigations import _generate_json_sse_events

        call_order: list[str] = []

        def reauth_check() -> bool:
            call_order.append("reauth")
            return False

        def fake_get_investigation(self, inv_id):  # noqa: ANN001
            call_order.append("poll")
            return InvestigationDetail.from_dict(_INV_RUNNING)

        with app.app_context(), patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation",
            new=fake_get_investigation,
        ):
            list(
                _generate_json_sse_events(
                    "http://mock-operator:8080",
                    5.0,
                    "inv-001",
                    1.0,
                    reauth_check=reauth_check,
                )
            )
        assert call_order == ["reauth"]  # poll never runs


# ---------------------------------------------------------------------------
# [T] `_build_sse_reauth_check()`
# ---------------------------------------------------------------------------


class TestBuildSseReauthCheck:
    def test_mode_none_returns_none(self) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        app = create_app(TestingConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            assert _build_sse_reauth_check() is None

    def test_local_mode_no_session_returns_none_defensively(self) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        app = create_app(_LocalConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            assert _build_sse_reauth_check() is None

    def test_local_mode_active_user_check_returns_true(
        self, seeded_store: IdentityStoreService
    ) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        record = seeded_store.create_local_user(user_name="zoe@corp.com", role="user")
        app = create_app(_LocalConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub=record.id)
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True

    def test_local_mode_detects_deactivation_between_calls(
        self, seeded_store: IdentityStoreService
    ) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        record = seeded_store.create_local_user(user_name="yara@corp.com", role="user")
        app = create_app(_LocalConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub=record.id)
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True

            seeded_store.deactivate_user(record.id)
            assert check() is False

    def test_local_mode_detects_role_demotion_below_gate(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """A demotion (still active, just no longer the required role)
        doesn't fail `resolve_role_for_identity` itself (it still resolves
        to "ok" with the new role) — the gate-drop enforcement below the
        required role belongs to `require_role`'s initial check, not the
        SSE re-auth hook, which only proves the identity remains VALID.
        Deactivation (proven above) is the deterministic termination
        signal this hook targets, per ADR §2/NFR25's "deactivated or drops
        below the gate" wording — demotion is still observable: the CHECK
        continues to succeed (role change without deactivation keeps
        `resolve_role_for_identity` at "ok"), consistent with `resolve_
        role_for_identity`'s contract."""
        record = seeded_store.create_local_user(user_name="wade@corp.com", role="admin")
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        app = create_app(_LocalConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub=record.id)
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True

            seeded_store.set_role(record.id, "user")
            assert check() is True  # still a valid identity, just demoted

    def test_session_expiring_mid_stream_check_returns_false(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """The captured identity's `exp` is re-validated on every check —
        proven by a session valid at stream-start whose absolute lifetime
        elapses before a later tick (`time.time()` advanced past `exp`,
        simulating a long-lived stream outliving the session)."""
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        record = seeded_store.create_local_user(user_name="vic@corp.com", role="user")
        app = create_app(_LocalConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub=record.id, exp_offset=3600)  # valid now
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True

            future = time.time() + 3601  # past the captured `exp`
            with patch("beeper_ui.routes.investigations.time.time", return_value=future):
                assert check() is False

    def test_oidc_without_scim_uses_role_snapshot(self) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        app = create_app(_OidcNoScimConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub="oidc-sub-1", role_snapshot="admin")
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True  # snapshot never expires mid-session

    def test_oidc_without_scim_expires_at_session_lifetime(self) -> None:
        from beeper_ui.routes.investigations import _build_sse_reauth_check

        app = create_app(_OidcNoScimConfig)
        with app.test_request_context("/api/v1/investigations/inv-1/events"):
            _set_raw_session_identity(sub="oidc-sub-2", exp_offset=3600)  # valid now
            check = _build_sse_reauth_check()
            assert check is not None
            assert check() is True

            future = time.time() + 3601  # past the captured `exp`
            with patch("beeper_ui.routes.investigations.time.time", return_value=future):
                assert check() is False
