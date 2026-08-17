"""Lifecycle guarantees (Task 8.8 — ADR 0002 §5.3/§7, NFR25):

- SCIM deactivation propagates to the resolver within the 60 s TTL bound
  (wired through the real store, exercised via
  `beeper_ui.middleware.permissions.resolve_role_for_identity()` — not
  just a direct store-attribute check).
- Adopt-and-link (ADR §5.2 HIGH-6), including the push-races-login
  ordering, verified end-to-end through the resolver.
- Group-rename recompute (a rename that moves a group into/out of
  `BEEPER_ADMIN_GROUPS` changes its current members' roles even with no
  add/remove op).
- Last-admin removal via SCIM triggers the zero-active-admins CRITICAL
  alarm and is NOT blocked (SCIM writes never 409 — only the admin-UI
  last-admin guard does, per ADR §5.3, and that's Task 8.7's surface, not
  this one's).
"""

from __future__ import annotations

import logging

import pytest

from beeper_ui.middleware.permissions import RoleResolution, resolve_role_for_identity
from beeper_ui.middleware.session import establish_session_identity
from beeper_ui.services.identity_store import ROLE_CACHE_TTL_SECONDS, reset_identity_store
from tests._scim_helpers import (
    ManualClock,
    ScimStrictConfig,
    ScimTestConfig,
    auth_headers,
    build_scim_app,
)

STORE_LOGGER = "beeper_ui.services.identity_store"


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-lifecycle-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


def _app_client(clock=None):
    app, store, fake = build_scim_app(ScimTestConfig, admin_groups=("Admins",), clock=clock)
    return app, app.test_client(), store, fake


def _resolve(app, *, sub: str, email: str, external_id: str | None = None) -> RoleResolution:
    """Exercise the SAME per-mode authority rule
    `resolve_request_identity()` uses (ADR §7), directly, inside a bare
    request context — mirrors `test_identity_resolver.py`'s pattern for
    unit-testing `resolve_role_for_identity()` without a full gated route
    round-trip."""
    with app.test_request_context("/"):
        identity = establish_session_identity(
            sub=sub, email=email, external_id=external_id, role_snapshot="user"
        )
        # `resolve_role_for_identity()` reads `current_app` — the request
        # context above provides it.
        return resolve_role_for_identity("oidc", identity)


class TestDeactivationPropagatesWithinTtl:
    def test_deactivation_denies_immediately_via_write_time_cache_invalidation(self) -> None:
        """Every store write invalidates the cache AT WRITE TIME
        (`_after_mutation`) — so propagation to the resolver is
        immediate, comfortably within NFR25's ≤60 s bound, for any
        caller sharing this process's store instance."""
        app, client, store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "dana@corp.com", "externalId": "ext-dana"},
        ).get_json()

        resolution = _resolve(app, sub="s1", email="dana@corp.com")
        assert resolution.status == "ok"
        assert resolution.role == "user"

        # SCIM deactivates (PATCH, string-boolean dialect).
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            },
        )
        assert resp.status_code == 200

        resolution = _resolve(app, sub="s1", email="dana@corp.com")
        assert resolution.status == "unauthenticated"
        assert store.get_by_id(created["id"], use_cache=False).active is False

    def test_deactivation_via_put_also_propagates(self) -> None:
        app, client, store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "eve@corp.com", "externalId": "ext-eve"},
        ).get_json()
        client.put(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={"userName": "eve@corp.com", "active": False},
        )
        resolution = _resolve(app, sub="s2", email="eve@corp.com")
        assert resolution.status == "unauthenticated"

    def test_hard_delete_degrades_a_live_session_to_default_user_not_strict(self) -> None:
        """DOCUMENTED FINDING (not a bug — the resolver's own, unmodified
        D2 semantics): a hard DELETE removes the store row entirely, so a
        subsequent lookup for that identity is indistinguishable from
        "never provisioned" — `resolve_role_for_identity()` (Task 8.3,
        out of this task's file surface) maps that to default `user`
        (non-strict), NOT to `"unauthenticated"`. ADR §5.3's "delete ⇒
        live sessions 401" is fully realized via DEACTIVATION (`active=
        false`, see the tests above) — which keeps a `found+inactive`
        row for the resolver's dedicated deny branch to see. Real Okta/
        Entra/Keycloak connectors deactivate before (or instead of) a
        hard delete during deprovisioning, so the ADR's guaranteed
        401-within-TTL path is the one actually exercised in practice;
        seeing default-`user` (never admin) rather than an outright deny
        for a hard-deleted-without-prior-deactivation identity is a
        narrower, but still safe, outcome — flagged in the task report
        for 8.9/the orchestrator, not silently asserted away here."""
        app, client, store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "frank@corp.com", "externalId": "ext-frank"},
        ).get_json()
        store.update_user(created["id"], role="admin")  # prove it's never re-admitted as admin
        client.delete(f"/scim/v2/Users/{created['id']}", headers=auth_headers())

        resolution = _resolve(app, sub="s3", email="frank@corp.com")
        assert resolution.status == "ok"
        assert resolution.role == "user"  # never admin, per D2 — but not denied outright

    def test_hard_delete_is_denied_outright_under_scim_strict(self) -> None:
        """Under `BEEPER_SCIM_STRICT=True`, the same store-miss resolves
        to `"forbidden"` (403) instead of default-`user` — a meaningful
        deny for deployments that opt into strict provisioning."""
        app, store, _fake = build_scim_app(ScimStrictConfig, admin_groups=("Admins",))
        client = app.test_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "iris@corp.com", "externalId": "ext-iris"},
        ).get_json()
        client.delete(f"/scim/v2/Users/{created['id']}", headers=auth_headers())

        resolution = _resolve(app, sub="s4", email="iris@corp.com")
        assert resolution.status == "forbidden"

    def test_cache_entry_itself_respects_the_60s_ttl_bound(self) -> None:
        """The underlying cache mechanism's own bound (ADR §2/§5.1's "one
        TTL program-wide"), wired through the store with a controllable
        clock — a stale cached miss self-corrects once 60 s of simulated
        time has passed, independent of whether a write ever invalidated
        it. Defense-in-depth for any path that reads the cache without a
        preceding write in the SAME process tick."""
        clock = ManualClock()
        app, client, store, _fake = _app_client(clock=clock)
        # First lookup with no user yet -> caches a "not found" miss.
        assert ROLE_CACHE_TTL_SECONDS == 60.0
        assert store.lookup("greg@corp.com", None) is None

        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "greg@corp.com", "externalId": "ext-greg"},
        ).get_json()
        # The POST's own write invalidated the cache already; use the
        # cache-bypassing read to confirm the record now exists, then
        # manually re-seed a stale cache entry to prove the TTL bound in
        # isolation from write-time invalidation.
        assert store.get_by_id(created["id"], use_cache=False) is not None
        store._cache_put(store._lookup_cache, ("greg@corp.com", None), None)  # simulate stale miss
        assert store.lookup("greg@corp.com", None) is None  # still cached (stale)
        clock.advance(ROLE_CACHE_TTL_SECONDS + 1)
        assert store.lookup("greg@corp.com", None) is not None  # expired -> fresh read


class TestAdoptAndLinkThroughResolver:
    def test_local_admin_adopted_by_scim_resolves_user_via_resolver(self) -> None:
        """ADR §5.2 HIGH-6's named test, proven through the resolver (not
        just a direct store-attribute check, which
        `test_scim_users.py::test_adopt_local_admin_recomputes_role_to_user`
        already covers at the store level)."""
        app, client, store, _fake = _app_client()
        store.create_local_user(user_name="alice@corp.com", role="admin")

        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-alice", "groups": []},
        )
        assert resp.status_code == 201

        resolution = _resolve(app, sub="alice-sub", email="alice@corp.com")
        assert resolution.status == "ok"
        assert resolution.role == "user"

    def test_push_races_login_then_admin_group_push_promotes_without_relogin(self) -> None:
        """The named ordering from ADR §5.2: login (store-miss) resolves
        `user` by default; a SCIM push (create, then a Group PATCH add)
        arrives after; re-resolving the SAME still-valid session — no
        re-login — now returns `admin`."""
        app, client, store, _fake = _app_client()

        # 1. "Login" happens before any SCIM record exists for this
        #    identity -> default `user` (store-miss, non-strict).
        first = _resolve(app, sub="hana-sub", email="hana@corp.com")
        assert first.status == "ok"
        assert first.role == "user"

        # 2. SCIM push arrives: create the user, then add to Admins.
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "hana@corp.com", "externalId": "ext-hana"},
        ).get_json()
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Admins"}
        ).get_json()
        client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "add", "path": "members", "value": [{"value": created["id"]}]}
                ],
            },
        )

        # 3. Re-resolve the SAME identity (no re-login) -> now admin.
        second = _resolve(app, sub="hana-sub", email="hana@corp.com")
        assert second.status == "ok"
        assert second.role == "admin"


class TestGroupRenameRecompute:
    def test_rename_into_admin_group_promotes_existing_members(self) -> None:
        app, client, store, _fake = _app_client()
        member = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "ivan@corp.com", "externalId": "ext-ivan"},
        ).get_json()
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Sales", "members": [{"value": member["id"]}]},
        ).get_json()
        assert store.get_by_id(member["id"], use_cache=False).role == "user"

        # Rename with membership UNCHANGED — no add/remove op at all.
        resp = client.put(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": member["id"]}]},
        )
        assert resp.status_code == 200
        assert store.get_by_id(member["id"], use_cache=False).role == "admin"
        resolution = _resolve(app, sub="ivan-sub", email="ivan@corp.com")
        assert resolution.role == "admin"

    def test_rename_out_of_admin_group_demotes_existing_members(self) -> None:
        app, client, store, _fake = _app_client()
        member = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "jill@corp.com", "externalId": "ext-jill"},
        ).get_json()
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": member["id"]}]},
        ).get_json()
        assert store.get_by_id(member["id"], use_cache=False).role == "admin"

        resp = client.put(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={"displayName": "RetiredAdmins", "members": [{"value": member["id"]}]},
        )
        assert resp.status_code == 200
        assert store.get_by_id(member["id"], use_cache=False).role == "user"


class TestLastAdminRemovalAlarmsButIsNotBlocked:
    def test_removing_the_last_admin_via_group_patch_is_200_not_409(self) -> None:
        app, client, store, _fake = _app_client()
        alice = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-alice"},
        ).get_json()
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        assert store.count_active_admins() == 1

        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "remove", "path": "members", "value": [{"value": alice["id"]}]}
                ],
            },
        )
        # SCIM writes are NEVER refused on last-admin grounds (ADR §5.3:
        # "a hard 409 to the IdP would page someone with a permanent
        # provisioning error") — that guard is admin-UI-only (Task 8.7).
        assert resp.status_code == 200
        assert store.get_by_id(alice["id"], use_cache=False).role == "user"

    def test_zero_active_admins_alarm_fires(self, caplog: pytest.LogCaptureFixture) -> None:
        app, client, store, _fake = _app_client()
        alice = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-alice"},
        ).get_json()
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        assert store.has_zero_active_admins() is False

        with caplog.at_level(logging.CRITICAL, logger=STORE_LOGGER):
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

        assert store.has_zero_active_admins() is True
        critical_records = [
            r for r in caplog.records if r.name == STORE_LOGGER and r.levelno == logging.CRITICAL
        ]
        assert critical_records, "expected a CRITICAL zero-active-admins log line"
        assert "Zero active admins" in critical_records[0].getMessage()

    def test_deactivating_the_last_admin_via_users_patch_also_alarms(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        app, client, store, _fake = _app_client()
        alice = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-alice"},
        ).get_json()
        store.update_user(alice["id"], role="admin")
        assert store.count_active_admins() == 1

        with caplog.at_level(logging.CRITICAL, logger=STORE_LOGGER):
            resp = client.patch(
                f"/scim/v2/Users/{alice['id']}",
                headers=auth_headers(),
                json={
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [{"op": "replace", "path": "active", "value": False}],
                },
            )
        assert resp.status_code == 200  # not blocked
        assert store.has_zero_active_admins() is True
        assert any(
            r.name == STORE_LOGGER and r.levelno == logging.CRITICAL for r in caplog.records
        )
