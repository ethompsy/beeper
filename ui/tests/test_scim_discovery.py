"""SCIM discovery documents (`ServiceProviderConfig`/`ResourceTypes`/
`Schemas`) + the 501 catch-all for unimplemented resources (Task 8.8 —
ADR 0002 §4).

Response shapes are schema-validated against RFC 7643 via `jsonschema`
(dev-only dependency — see `tests/_scim_json_schemas.py` and
`ui/pyproject.toml`).
"""

from __future__ import annotations

import jsonschema
import pytest

from beeper_ui.services.identity_store import reset_identity_store
from tests._scim_helpers import ScimTestConfig, auth_headers, build_scim_app
from tests._scim_json_schemas import (
    GROUP_RESOURCE_SCHEMA,
    RESOURCE_TYPE_SCHEMA,
    SCHEMA_DEFINITION_SCHEMA,
    SCIM_ERROR_SCHEMA,
    SERVICE_PROVIDER_CONFIG_SCHEMA,
    USER_RESOURCE_SCHEMA,
    list_response_schema,
)


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-discovery-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


def _client():
    app, _store, _fake = build_scim_app(ScimTestConfig)
    return app.test_client()


class TestServiceProviderConfig:
    def test_shape_matches_rfc7643(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/ServiceProviderConfig", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/scim+json")
        jsonschema.validate(resp.get_json(), SERVICE_PROVIDER_CONFIG_SCHEMA)

    def test_patch_and_filter_are_advertised_supported(self) -> None:
        client = _client()
        body = client.get("/scim/v2/ServiceProviderConfig", headers=auth_headers()).get_json()
        assert body["patch"]["supported"] is True
        assert body["filter"]["supported"] is True
        assert body["bulk"]["supported"] is False

    def test_bearer_auth_scheme_advertised(self) -> None:
        client = _client()
        body = client.get("/scim/v2/ServiceProviderConfig", headers=auth_headers()).get_json()
        schemes = {s["type"] for s in body["authenticationSchemes"]}
        assert "oauthbearertoken" in schemes


class TestResourceTypes:
    def test_list_contains_user_and_group(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/ResourceTypes", headers=auth_headers())
        assert resp.status_code == 200
        body = resp.get_json()
        jsonschema.validate(body, list_response_schema(RESOURCE_TYPE_SCHEMA))
        names = {r["name"] for r in body["Resources"]}
        assert names == {"User", "Group"}

    def test_user_resource_type_detail(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/ResourceTypes/User", headers=auth_headers())
        assert resp.status_code == 200
        body = resp.get_json()
        jsonschema.validate(body, RESOURCE_TYPE_SCHEMA)
        assert body["endpoint"] == "/Users"
        assert body["schema"] == "urn:ietf:params:scim:schemas:core:2.0:User"

    def test_group_resource_type_detail(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/ResourceTypes/Group", headers=auth_headers())
        body = resp.get_json()
        assert body["endpoint"] == "/Groups"

    def test_unknown_resource_type_404(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/ResourceTypes/Widget", headers=auth_headers())
        assert resp.status_code == 404
        jsonschema.validate(resp.get_json(), SCIM_ERROR_SCHEMA)


class TestSchemas:
    def test_list_contains_user_and_group_schemas(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/Schemas", headers=auth_headers())
        body = resp.get_json()
        jsonschema.validate(body, list_response_schema(SCHEMA_DEFINITION_SCHEMA))
        ids = {s["id"] for s in body["Resources"]}
        assert ids == {
            "urn:ietf:params:scim:schemas:core:2.0:User",
            "urn:ietf:params:scim:schemas:core:2.0:Group",
        }

    def test_user_schema_detail(self) -> None:
        client = _client()
        resp = client.get(
            "/scim/v2/Schemas/urn:ietf:params:scim:schemas:core:2.0:User", headers=auth_headers()
        )
        assert resp.status_code == 200
        body = resp.get_json()
        jsonschema.validate(body, SCHEMA_DEFINITION_SCHEMA)
        attr_names = {a["name"] for a in body["attributes"]}
        assert {"userName", "active", "emails"}.issubset(attr_names)

    def test_unknown_schema_id_404(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/Schemas/urn:unknown:schema", headers=auth_headers())
        assert resp.status_code == 404


class TestUserAndGroupResourceShapesConformToSchema:
    def test_created_user_matches_schema(self) -> None:
        client = _client()
        resp = client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "shape@corp.com", "externalId": "ext-shape"},
        )
        jsonschema.validate(resp.get_json(), USER_RESOURCE_SCHEMA)

    def test_created_group_matches_schema(self) -> None:
        client = _client()
        resp = client.post(
            "/scim/v2/Groups", headers=auth_headers(), json={"displayName": "ShapeGroup"}
        )
        jsonschema.validate(resp.get_json(), GROUP_RESOURCE_SCHEMA)

    def test_users_list_response_matches_schema(self) -> None:
        client = _client()
        client.post(
            "/scim/v2/Users",
            headers=auth_headers(),
            json={"userName": "listshape@corp.com", "externalId": "ext-ls"},
        )
        resp = client.get("/scim/v2/Users", headers=auth_headers())
        jsonschema.validate(resp.get_json(), list_response_schema(USER_RESOURCE_SCHEMA))


class TestCatchAllNotImplemented:
    def test_bulk_returns_501_scim_error(self) -> None:
        client = _client()
        resp = client.post("/scim/v2/Bulk", headers=auth_headers(), json={})
        assert resp.status_code == 501
        jsonschema.validate(resp.get_json(), SCIM_ERROR_SCHEMA)

    def test_me_returns_501(self) -> None:
        client = _client()
        resp = client.get("/scim/v2/Me", headers=auth_headers())
        assert resp.status_code == 501

    def test_static_routes_are_not_shadowed_by_catch_all(self) -> None:
        """Regression guard: the `<path:rest>` catch-all is registered
        LAST but must never win over a real static route."""
        client = _client()
        resp = client.get("/scim/v2/Users", headers=auth_headers())
        assert resp.status_code == 200
