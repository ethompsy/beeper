"""Audit logging for SCIM provisioning mutations (Task 8.8 — ADR 0002 §4,
FR58): every mutation logged with a token fingerprint (never the raw
token), admin-group membership changes flagged distinctly.
"""

from __future__ import annotations

import hashlib
import logging

import pytest

from beeper_ui.services.identity_store import reset_identity_store
from tests._scim_helpers import SCIM_TOKEN, ScimTestConfig, auth_headers, build_scim_app

AUDIT_LOGGER = "beeper_ui.scim.audit"
EXPECTED_FINGERPRINT = hashlib.sha256(SCIM_TOKEN.encode("utf-8")).hexdigest()[:8]


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-audit-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


def _app_client():
    app, store, fake = build_scim_app(ScimTestConfig, admin_groups=("Admins",))
    return app, app.test_client(), store, fake


def _create_user(client, user_name: str, external_id: str) -> dict:
    return client.post(
        "/scim/v2/Users",
        headers=auth_headers(),
        json={"userName": user_name, "externalId": external_id},
    ).get_json()


class TestFingerprintNeverRawToken:
    def test_create_user_logs_fingerprint_not_token(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Users",
                headers=auth_headers(),
                json={"userName": "audit1@corp.com", "externalId": "ext-1"},
            )
        records = [r for r in caplog.records if r.name == AUDIT_LOGGER]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "SCIM audit:" in message
        assert f"token_fp={EXPECTED_FINGERPRINT}" in message
        assert SCIM_TOKEN not in message
        assert "op=create" in message
        assert "resource_type=User" in message

    def test_raw_token_never_appears_in_any_captured_log_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Greps EVERY captured log record across a full mutation
        sequence, not just the audit line — the raw token must never
        leak anywhere, including error paths."""
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.DEBUG):
            client.post(
                "/scim/v2/Users",
                headers=auth_headers(),
                json={"userName": "audit2@corp.com", "externalId": "ext-2"},
            )
            client.post("/scim/v2/Users", headers=auth_headers("wrong-token"), json={})
            client.get("/scim/v2/Users", headers=auth_headers())
        for record in caplog.records:
            assert SCIM_TOKEN not in record.getMessage()

    def test_fingerprint_is_stable_sha256_first_8_hex_chars(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        assert len(EXPECTED_FINGERPRINT) == 8
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Users",
                headers=auth_headers(),
                json={"userName": "audit3@corp.com", "externalId": "ext-3"},
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert f"token_fp={EXPECTED_FINGERPRINT}" in message


class TestAdminGroupChangeFlagging:
    def test_user_create_no_group_not_flagged(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Users",
                headers=auth_headers(),
                json={"userName": "plain@corp.com", "externalId": "ext-p"},
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "admin_group_change=False" in message

    def test_group_create_with_admin_members_flagged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Groups",
                headers=auth_headers(),
                json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
            )
        records = [r for r in caplog.records if r.name == AUDIT_LOGGER]
        group_record = next(r for r in records if "resource_type=Group" in r.getMessage())
        assert "admin_group_change=True" in group_record.getMessage()
        assert "op=create" in group_record.getMessage()

    def test_group_create_non_admin_members_not_flagged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Groups",
                headers=auth_headers(),
                json={"displayName": "Sales", "members": [{"value": alice["id"]}]},
            )
        records = [r for r in caplog.records if r.name == AUDIT_LOGGER]
        group_record = next(r for r in records if "resource_type=Group" in r.getMessage())
        assert "admin_group_change=False" in group_record.getMessage()

    def test_group_patch_add_to_admin_group_flagged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Admins"}
        ).get_json()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.patch(
                f"/scim/v2/Groups/{group['id']}",
                headers=auth_headers(),
                json={
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [
                        {"op": "add", "path": "members", "value": [{"value": alice["id"]}]}
                    ],
                },
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "op=patch" in message
        assert "admin_group_change=True" in message

    def test_group_patch_remove_last_admin_flagged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.patch(
                f"/scim/v2/Groups/{group['id']}",
                headers=auth_headers(),
                json={
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [
                        {"op": "remove", "path": "members", "value": [{"value": alice["id"]}]}
                    ],
                },
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "admin_group_change=True" in message

    def test_delete_active_admin_user_flagged(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        store.update_user(alice["id"], role="admin")
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.delete(f"/scim/v2/Users/{alice['id']}", headers=auth_headers())
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "op=delete" in message
        assert "admin_group_change=True" in message

    def test_delete_non_admin_user_not_flagged(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, _store, _fake = _app_client()
        bob = _create_user(client, "bob@corp.com", "ext-b")
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.delete(f"/scim/v2/Users/{bob['id']}", headers=auth_headers())
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "admin_group_change=False" in message

    def test_delete_admin_group_with_members_flagged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.delete(f"/scim/v2/Groups/{group['id']}", headers=auth_headers())
        records = [r for r in caplog.records if r.name == AUDIT_LOGGER]
        delete_record = next(r for r in records if "op=delete" in r.getMessage())
        assert "admin_group_change=True" in delete_record.getMessage()

    def test_user_put_profile_only_not_flagged(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        store.update_user(alice["id"], role="admin")
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.put(
                f"/scim/v2/Users/{alice['id']}",
                headers=auth_headers(),
                json={"userName": "alice@corp.com", "displayName": "Alice A", "active": True},
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "admin_group_change=False" in message


class TestAuditLogTarget:
    def test_target_is_username_for_users(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Users",
                headers=auth_headers(),
                json={"userName": "target@corp.com", "externalId": "ext-t"},
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "target=target@corp.com" in message

    def test_target_is_display_name_for_groups(self, caplog: pytest.LogCaptureFixture) -> None:
        _app, client, _store, _fake = _app_client()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            client.post(
                "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "TargetGroup"}
            )
        message = [r for r in caplog.records if r.name == AUDIT_LOGGER][-1].getMessage()
        assert "target=TargetGroup" in message


class TestAuditLoggerEmissionConfig:
    """Live-validation finding (Task 8.9): audit records must be emitted by
    the DEPLOYED process regardless of ambient logging config — caplog-based
    tests bypass handlers and could not catch a dropped-trail regression."""

    def test_audit_logger_has_dedicated_handler_at_info(self):
        import logging

        from beeper_ui.routes import scim_helpers

        log = scim_helpers.logger
        assert log.handlers, "audit logger must own a handler (not rely on root)"
        assert log.level == logging.INFO
        assert log.propagate is True  # caplog capture depends on propagation

    def test_audit_record_reaches_its_handler(self):
        import io
        import logging

        from beeper_ui.routes import scim_helpers

        buf = io.StringIO()
        extra = logging.StreamHandler(buf)
        scim_helpers.logger.addHandler(extra)
        try:
            scim_helpers.logger.info("audit-emission-probe")
        finally:
            scim_helpers.logger.removeHandler(extra)
        assert "audit-emission-probe" in buf.getvalue()
