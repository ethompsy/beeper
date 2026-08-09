"""`/scim/v2/Groups` CRUD, filter, PUT, membership PATCH — BOTH vendor
dialects, DELETE (Task 8.8 — ADR 0002 §4, FR57).
"""

from __future__ import annotations

import pytest

from beeper_ui.services.identity_store import reset_identity_store
from tests._scim_helpers import ScimTestConfig, auth_headers, build_scim_app


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-group-tests")
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


class TestCreateGroup:
    def test_create_group_no_members_201(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Engineers"}
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["displayName"] == "Engineers"
        assert body["members"] == []
        assert resp.headers["Location"] == f"/scim/v2/Groups/{body['id']}"

    def test_create_group_missing_display_name_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post("/scim/v2/Groups", headers=auth_headers(), json={})
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidValue"

    def test_create_duplicate_display_name_409(self) -> None:
        _app, client, _store, _fake = _app_client()
        client.post("/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Dup"})
        resp = client.post("/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Dup"})
        assert resp.status_code == 409
        assert resp.get_json()["scimType"] == "uniqueness"

    def test_create_group_with_initial_members_grants_admin_role(self) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        resp = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        )
        assert resp.status_code == 201
        assert store.get_by_id(alice["id"], use_cache=False).role == "admin"


class TestListAndFilterGroups:
    def test_filter_display_name_eq(self) -> None:
        _app, client, _store, _fake = _app_client()
        client.post("/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Sales"})
        client.post("/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Marketing"})
        resp = client.get('/scim/v2/Groups?filter=displayName eq "Sales"', headers=auth_headers())
        body = resp.get_json()
        assert body["totalResults"] == 1
        assert body["Resources"][0]["displayName"] == "Sales"

    def test_filter_display_name_case_insensitive_value(self) -> None:
        _app, client, _store, _fake = _app_client()
        client.post("/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Sales"})
        resp = client.get('/scim/v2/Groups?filter=displayName eq "sales"', headers=auth_headers())
        assert resp.get_json()["totalResults"] == 1

    def test_excluded_attributes_members(self) -> None:
        """ADR §4 named quirk: honor `excludedAttributes=members` on
        `/Groups` GET."""
        _app, client, _store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Sales", "members": [{"value": alice["id"]}]},
        )
        resp = client.get("/scim/v2/Groups?excludedAttributes=members", headers=auth_headers())
        for resource in resp.get_json()["Resources"]:
            assert "members" not in resource

    def test_unsupported_filter_attribute_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.get('/scim/v2/Groups?filter=owner eq "x"', headers=auth_headers())
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidFilter"


class TestGetGroup:
    def test_get_by_id_200(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Ops"}
        ).get_json()
        resp = client.get(f"/scim/v2/Groups/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.get_json()["displayName"] == "Ops"

    def test_get_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.get("/scim/v2/Groups/nope", headers=auth_headers())
        assert resp.status_code == 404


class TestPutGroup:
    def test_put_replaces_members(self) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        bob = _create_user(client, "bob@corp.com", "ext-b")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        assert store.get_by_id(alice["id"], use_cache=False).role == "admin"

        resp = client.put(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": bob["id"]}]},
        )
        assert resp.status_code == 200
        member_ids = {m["value"] for m in resp.get_json()["members"]}
        assert member_ids == {bob["id"]}
        # alice was removed -> demoted; bob was added -> promoted.
        assert store.get_by_id(alice["id"], use_cache=False).role == "user"
        assert store.get_by_id(bob["id"], use_cache=False).role == "admin"

    def test_put_rename_updates_same_row_not_a_fork(self) -> None:
        """Regression guard for the `update_group()` fix: a PUT that
        renames `displayName` must update the SAME group row, never
        silently create a second one via `upsert_group()`'s
        external-id/display-name lookup semantics."""
        _app, client, store, _fake = _app_client()
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "OldName"}
        ).get_json()
        resp = client.put(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={"displayName": "NewName", "members": []},
        )
        assert resp.status_code == 200
        assert resp.get_json()["id"] == group["id"]
        all_groups = store.list_groups()
        assert len(all_groups) == 1
        assert all_groups[0].display_name == "NewName"

    def test_put_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.put(
            "/scim/v2/Groups/nope", headers=auth_headers(), json={"displayName": "X"}
        )
        assert resp.status_code == 404


class TestPatchGroupMembershipBothDialects:
    """Parametrized over Okta's array-value dialect and Entra's
    filtered-path dialect (ADR §4: "both vendor membership-delta
    dialects")."""

    def _okta_add(self, user_id: str) -> dict:
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "add", "path": "members", "value": [{"value": user_id}]}],
        }

    def _okta_remove(self, user_id: str) -> dict:
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "remove", "path": "members", "value": [{"value": user_id}]}],
        }

    def _entra_add(self, user_id: str) -> dict:
        # Entra's add dialect matches Okta's shape in practice; the
        # differentiator is specifically the filtered-path REMOVE below.
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "add", "path": "members", "value": [{"value": user_id}]}],
        }

    def _entra_remove(self, user_id: str) -> dict:
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "remove", "path": f'members[value eq "{user_id}"]'}],
        }

    @pytest.mark.parametrize("dialect", ["okta", "entra"])
    def test_add_member_promotes_to_admin(self, dialect: str) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Admins"}
        ).get_json()

        add_body = (
            self._okta_add(alice["id"]) if dialect == "okta" else self._entra_add(alice["id"])
        )
        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}", headers=auth_headers(), json=add_body
        )
        assert resp.status_code == 200
        member_ids = {m["value"] for m in resp.get_json()["members"]}
        assert alice["id"] in member_ids
        assert store.get_by_id(alice["id"], use_cache=False).role == "admin"

    @pytest.mark.parametrize("dialect", ["okta", "entra"])
    def test_remove_member_demotes_from_admin(self, dialect: str) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()
        assert store.get_by_id(alice["id"], use_cache=False).role == "admin"

        remove_body = (
            self._okta_remove(alice["id"]) if dialect == "okta" else self._entra_remove(alice["id"])
        )
        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}", headers=auth_headers(), json=remove_body
        )
        assert resp.status_code == 200
        member_ids = {m["value"] for m in resp.get_json()["members"]}
        assert alice["id"] not in member_ids
        assert store.get_by_id(alice["id"], use_cache=False).role == "user"


class TestPatchGroupOtherShapes:
    def test_replace_full_membership(self) -> None:
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        bob = _create_user(client, "bob@corp.com", "ext-b")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()

        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "replace", "path": "members", "value": [{"value": bob["id"]}]}
                ],
            },
        )
        member_ids = {m["value"] for m in resp.get_json()["members"]}
        assert member_ids == {bob["id"]}
        assert store.get_by_id(alice["id"], use_cache=False).role == "user"
        assert store.get_by_id(bob["id"], use_cache=False).role == "admin"

    def test_remove_all_members_no_filter_no_value(self) -> None:
        """RFC 7644 §3.5.2.2: a `remove` on plain `path: "members"` with
        NO value removes every member."""
        _app, client, store, _fake = _app_client()
        alice = _create_user(client, "alice@corp.com", "ext-a")
        group = client.post(
            "/scim/v2/Groups",
            headers=auth_headers(),
            json={"displayName": "Admins", "members": [{"value": alice["id"]}]},
        ).get_json()

        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "remove", "path": "members"}],
            },
        )
        assert resp.get_json()["members"] == []
        assert store.get_by_id(alice["id"], use_cache=False).role == "user"

    def test_path_less_replace_with_members_and_display_name(self) -> None:
        _app, client, _store, _fake = _app_client()
        bob = _create_user(client, "bob@corp.com", "ext-b")
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Sales"}
        ).get_json()
        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {
                        "op": "replace",
                        "value": {"displayName": "SalesTeam", "members": [{"value": bob["id"]}]},
                    }
                ],
            },
        )
        body = resp.get_json()
        assert body["displayName"] == "SalesTeam"
        assert {m["value"] for m in body["members"]} == {bob["id"]}

    def test_patch_unknown_group_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.patch(
            "/scim/v2/Groups/nope",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "add", "path": "members", "value": [{"value": "x"}]}],
            },
        )
        assert resp.status_code == 404

    def test_patch_missing_operations_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "X"}
        ).get_json()
        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]},
        )
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidPath"

    def test_patch_membership_referencing_unknown_user_id_tolerated(self) -> None:
        """SCIM does not require rejecting an unknown member reference —
        Okta/Entra push Users and Groups out of strict order."""
        _app, client, _store, _fake = _app_client()
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Admins"}
        ).get_json()
        resp = client.patch(
            f"/scim/v2/Groups/{group['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "add", "path": "members", "value": [{"value": "unknown-user-id"}]}
                ],
            },
        )
        assert resp.status_code == 200
        assert "unknown-user-id" in {m["value"] for m in resp.get_json()["members"]}


class TestDeleteGroup:
    def test_delete_returns_204_and_hard_deletes(self) -> None:
        _app, client, store, _fake = _app_client()
        group = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "Temp"}
        ).get_json()
        resp = client.delete(f"/scim/v2/Groups/{group['id']}", headers=auth_headers())
        assert resp.status_code == 204
        assert store.get_group_by_id(group["id"]) is None

    def test_delete_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.delete("/scim/v2/Groups/nope", headers=auth_headers())
        assert resp.status_code == 404
