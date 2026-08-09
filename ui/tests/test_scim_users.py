"""`/scim/v2/Users` CRUD, filter, PUT/PATCH, deactivate, DELETE
(Task 8.8 — ADR 0002 §4, FR57).
"""

from __future__ import annotations

import pytest

from beeper_ui.services.identity_store import reset_identity_store
from tests._scim_helpers import ScimTestConfig, auth_headers, build_scim_app


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-user-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


def _app_client():
    app, store, fake = build_scim_app(ScimTestConfig)
    return app, app.test_client(), store, fake


class TestCreateUser:
    def test_create_minimal_user_201(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-1"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["userName"] == "alice@corp.com"
        assert body["externalId"] == "ext-1"
        assert body["active"] is True
        assert body["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:User"]
        assert resp.headers["Location"] == f"/scim/v2/Users/{body['id']}"

    def test_create_missing_username_and_email_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post("/scim/v2/Users", headers=auth_headers(), json={"externalId": "e1"})
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidValue"

    def test_create_missing_external_id_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post(
            "/scim/v2/Users", headers=auth_headers(), json={"userName": "bob@corp.com"}
        )
        assert resp.status_code == 400

    def test_create_duplicate_scim_username_409(self) -> None:
        _app, client, _store, _fake = _app_client()
        client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "dup@corp.com", "externalId": "ext-1"},
        )
        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "dup@corp.com", "externalId": "ext-2"},
        )
        assert resp.status_code == 409
        assert resp.get_json()["scimType"] == "uniqueness"

    def test_create_body_must_be_json_object_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.post(
            "/scim/v2/Users",
            headers={**auth_headers(), "Content-Type": "application/json"},
            data="not json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidSyntax"

    def test_entra_username_falls_back_to_primary_email(self) -> None:
        """Entra's userName/emails mapping quirk: some connectors omit
        `userName` entirely and rely on `emails` — the store's canonical
        `userName` is derived from the primary email in that case."""
        _app, client, _store, _fake = _app_client()
        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"externalId": "ext-e1", "emails": [{"value": "carol@corp.com", "primary": True}]},
        )
        assert resp.status_code == 201
        assert resp.get_json()["userName"] == "carol@corp.com"

    def test_adopt_local_admin_recomputes_role_to_user(self) -> None:
        """ADR §5.2 HIGH-6 named test, exercised end-to-end through the
        SCIM route: a local-origin admin gets adopted by a SCIM POST that
        places them in no admin group — role is recomputed to `user`,
        discarding the prior local role."""
        _app, client, store, _fake = _app_client()
        local_admin = store.create_local_user(user_name="alice@corp.com", role="admin")
        assert local_admin.role == "admin"

        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-alice", "groups": []},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["id"] == local_admin.id  # adopted the SAME record, not a new one
        adopted = store.get_by_id(local_admin.id, use_cache=False)
        assert adopted is not None
        assert adopted.role == "user"
        assert adopted.origin == "scim"
        assert adopted.password_hash is None or adopted.password_hash == local_admin.password_hash


class TestListAndFilterUsers:
    def _seed(self, client):
        client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "alice@corp.com", "externalId": "ext-1", "displayName": "Alice A"},
        )
        client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "bob@corp.com", "externalId": "ext-2", "displayName": "Bob B"},
        )

    def test_list_all_users(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get("/scim/v2/Users", headers=auth_headers())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["totalResults"] == 2
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
        assert len(body["Resources"]) == 2

    def test_filter_username_eq(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get(
            '/scim/v2/Users?filter=userName eq "alice@corp.com"', headers=auth_headers()
        )
        body = resp.get_json()
        assert body["totalResults"] == 1
        assert body["Resources"][0]["userName"] == "alice@corp.com"

    def test_filter_username_case_insensitive_attribute_name(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get(
            '/scim/v2/Users?filter=USERNAME eq "alice@corp.com"', headers=auth_headers()
        )
        assert resp.get_json()["totalResults"] == 1

    def test_filter_external_id_eq(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get('/scim/v2/Users?filter=externalId eq "ext-2"', headers=auth_headers())
        body = resp.get_json()
        assert body["totalResults"] == 1
        assert body["Resources"][0]["userName"] == "bob@corp.com"

    def test_filter_dedupe_no_match_returns_empty(self) -> None:
        """The "dedupe filter" step of the golden Okta sequence — a
        provisioning connector checks for an existing user before
        creating one; no match must be an empty (not error) result."""
        _app, client, _store, _fake = _app_client()
        resp = client.get(
            '/scim/v2/Users?filter=userName eq "nobody@corp.com"', headers=auth_headers()
        )
        assert resp.status_code == 200
        assert resp.get_json()["totalResults"] == 0

    def test_unsupported_filter_attribute_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.get('/scim/v2/Users?filter=nickName eq "x"', headers=auth_headers())
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidFilter"

    def test_malformed_filter_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.get("/scim/v2/Users?filter=userName%20%3D%3D%20x", headers=auth_headers())
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidFilter"

    def test_pagination_start_index_and_count(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get("/scim/v2/Users?startIndex=2&count=1", headers=auth_headers())
        body = resp.get_json()
        assert body["startIndex"] == 2
        assert body["itemsPerPage"] == 1
        assert body["totalResults"] == 2

    def test_excluded_attributes_removes_field(self) -> None:
        _app, client, _store, _fake = _app_client()
        self._seed(client)
        resp = client.get("/scim/v2/Users?excludedAttributes=groups", headers=auth_headers())
        for resource in resp.get_json()["Resources"]:
            assert "groups" not in resource


class TestGetUser:
    def test_get_by_id_200(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "dana@corp.com", "externalId": "ext-d"},
        ).get_json()
        resp = client.get(f"/scim/v2/Users/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.get_json()["userName"] == "dana@corp.com"

    def test_get_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.get("/scim/v2/Users/does-not-exist", headers=auth_headers())
        assert resp.status_code == 404
        assert resp.get_json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]


class TestPutUser:
    def _create(self, client):
        return client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "erin@corp.com", "externalId": "ext-e", "displayName": "Erin"},
        ).get_json()

    def test_put_deactivates_user(self) -> None:
        """The golden Okta sequence's final step: PUT with `active: false`."""
        _app, client, store, _fake = _app_client()
        created = self._create(client)
        resp = client.put(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={"userName": "erin@corp.com", "active": False},
        )
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False
        assert store.get_by_id(created["id"], use_cache=False).active is False

    def test_put_updates_display_name_and_emails(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = self._create(client)
        resp = client.put(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={
                "userName": "erin@corp.com",
                "displayName": "Erin Renamed",
                "emails": [{"value": "erin.new@corp.com", "primary": True}],
                "active": True,
            },
        )
        body = resp.get_json()
        assert body["displayName"] == "Erin Renamed"
        assert body["emails"][0]["value"] == "erin.new@corp.com"

    def test_put_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.put(
            "/scim/v2/Users/nope", headers=auth_headers(), json={"userName": "x", "active": True}
        )
        assert resp.status_code == 404

    def test_put_rename_conflicting_username_409(self) -> None:
        _app, client, _store, _fake = _app_client()
        client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "taken@corp.com", "externalId": "ext-taken"},
        )
        created = self._create(client)
        resp = client.put(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={"userName": "taken@corp.com", "active": True},
        )
        assert resp.status_code == 409
        assert resp.get_json()["scimType"] == "uniqueness"

    def test_put_does_not_change_role(self) -> None:
        """SCIM Users PUT/PATCH never carries `role` — it's derived
        exclusively from group membership (FR56) and must be untouched by
        a profile-only PUT."""
        _app, client, store, _fake = _app_client()
        created = self._create(client)
        store.update_user(created["id"], role="admin")
        client.put(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={"userName": "erin@corp.com", "displayName": "Erin Two", "active": True},
        )
        assert store.get_by_id(created["id"], use_cache=False).role == "admin"


class TestPatchUser:
    def _create(self, client):
        return client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "frank@corp.com", "externalId": "ext-f"},
        ).get_json()

    @pytest.mark.parametrize(
        "patch_body",
        [
            pytest.param(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [{"op": "replace", "path": "active", "value": False}],
                },
                id="native-boolean-replace-with-path",
            ),
            pytest.param(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [{"op": "Replace", "path": "active", "value": "false"}],
                },
                id="okta-style-string-boolean-and-op-case",
            ),
            pytest.param(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [{"op": "replace", "value": {"active": False}}],
                },
                id="path-less-replace-with-object-value",
            ),
        ],
    )
    def test_patch_deactivates_active_field(self, patch_body: dict) -> None:
        _app, client, store, _fake = _app_client()
        created = self._create(client)
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}", headers=auth_headers(), json=patch_body
        )
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False
        assert store.get_by_id(created["id"], use_cache=False).active is False

    def test_patch_display_name(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = self._create(client)
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "displayName", "value": "Frank Two"}],
            },
        )
        assert resp.get_json()["displayName"] == "Frank Two"

    def test_patch_unknown_attribute_ignored_not_error(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = self._create(client)
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "nickName", "value": "Frankie"}],
            },
        )
        assert resp.status_code == 200

    def test_patch_missing_operations_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = self._create(client)
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]},
        )
        assert resp.status_code == 400
        assert resp.get_json()["scimType"] == "invalidPath"

    def test_patch_invalid_op_400(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = self._create(client)
        resp = client.patch(
            f"/scim/v2/Users/{created['id']}",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "move", "path": "active", "value": True}],
            },
        )
        assert resp.status_code == 400

    def test_patch_unknown_user_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.patch(
            "/scim/v2/Users/nope",
            headers=auth_headers(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            },
        )
        assert resp.status_code == 404


class TestDeleteUser:
    def test_delete_returns_204_and_hard_deletes(self) -> None:
        _app, client, store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "gina@corp.com", "externalId": "ext-g"},
        ).get_json()
        resp = client.delete(f"/scim/v2/Users/{created['id']}", headers=auth_headers())
        assert resp.status_code == 204
        assert resp.data == b""
        assert store.get_by_id(created["id"], use_cache=False) is None

    def test_delete_is_idempotent_404_on_second_call(self) -> None:
        _app, client, _store, _fake = _app_client()
        created = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "hank@corp.com", "externalId": "ext-h"},
        ).get_json()
        client.delete(f"/scim/v2/Users/{created['id']}", headers=auth_headers())
        resp = client.delete(f"/scim/v2/Users/{created['id']}", headers=auth_headers())
        assert resp.status_code == 404

    def test_delete_unknown_id_404(self) -> None:
        _app, client, _store, _fake = _app_client()
        resp = client.delete("/scim/v2/Users/does-not-exist", headers=auth_headers())
        assert resp.status_code == 404
