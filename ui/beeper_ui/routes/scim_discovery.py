"""Static SCIM 2.0 discovery documents (Task 8.8 — ADR 0002 §4).

`ServiceProviderConfig` (RFC 7643 §5), `ResourceTypes` (§6), and `Schemas`
(§7) — the three discovery endpoints Okta/Entra/Keycloak provisioning
connectors probe during setup to learn what this service supports. All
three are static (no store access), kept in their own module so `scim.py`
reads as routing + orchestration rather than a wall of schema literals.
"""

from __future__ import annotations

from typing import Any

from beeper_ui.routes.scim_helpers import GROUP_SCHEMA, USER_SCHEMA

SERVICE_PROVIDER_CONFIG: dict[str, Any] = {
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
    "patch": {"supported": True},
    "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
    "filter": {"supported": True, "maxResults": 200},
    "changePassword": {"supported": False},
    "sort": {"supported": False},
    "etag": {"supported": False},
    "authenticationSchemes": [
        {
            "type": "oauthbearertoken",
            "name": "OAuth Bearer Token",
            "description": (
                "Authentication scheme using a long-lived bearer token "
                "issued out-of-band via a Kubernetes Secret."
            ),
            "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
            "primary": True,
        }
    ],
    "meta": {
        "resourceType": "ServiceProviderConfig",
        "location": "/scim/v2/ServiceProviderConfig",
    },
}

USER_RESOURCE_TYPE: dict[str, Any] = {
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
    "id": "User",
    "name": "User",
    "endpoint": "/Users",
    "description": "User Account",
    "schema": USER_SCHEMA,
    "schemaExtensions": [],
    "meta": {"resourceType": "ResourceType", "location": "/scim/v2/ResourceTypes/User"},
}

GROUP_RESOURCE_TYPE: dict[str, Any] = {
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
    "id": "Group",
    "name": "Group",
    "endpoint": "/Groups",
    "description": "Group",
    "schema": GROUP_SCHEMA,
    "schemaExtensions": [],
    "meta": {"resourceType": "ResourceType", "location": "/scim/v2/ResourceTypes/Group"},
}

RESOURCE_TYPES_BY_NAME: dict[str, dict[str, Any]] = {
    "User": USER_RESOURCE_TYPE,
    "Group": GROUP_RESOURCE_TYPE,
}

_STRING_ATTR = {
    "type": "string",
    "multiValued": False,
    "required": False,
    "caseExact": False,
    "mutability": "readWrite",
    "returned": "default",
    "uniqueness": "none",
}

USER_SCHEMA_DEF: dict[str, Any] = {
    "id": USER_SCHEMA,
    "name": "User",
    "description": "User Account",
    "attributes": [
        {**_STRING_ATTR, "name": "userName", "required": True, "uniqueness": "server"},
        {**_STRING_ATTR, "name": "displayName"},
        {
            "name": "emails",
            "type": "complex",
            "multiValued": True,
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
            "subAttributes": [
                {**_STRING_ATTR, "name": "value"},
                {
                    "name": "primary",
                    "type": "boolean",
                    "multiValued": False,
                    "required": False,
                    "mutability": "readWrite",
                    "returned": "default",
                    "uniqueness": "none",
                },
            ],
        },
        {
            "name": "active",
            "type": "boolean",
            "multiValued": False,
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
        },
        {
            "name": "groups",
            "type": "complex",
            "multiValued": True,
            "required": False,
            "mutability": "readOnly",
            "returned": "default",
            "uniqueness": "none",
            "subAttributes": [
                {
                    **_STRING_ATTR,
                    "name": "value",
                    "mutability": "readOnly",
                }
            ],
        },
    ],
    "meta": {"resourceType": "Schema", "location": f"/scim/v2/Schemas/{USER_SCHEMA}"},
}

GROUP_SCHEMA_DEF: dict[str, Any] = {
    "id": GROUP_SCHEMA,
    "name": "Group",
    "description": "Group",
    "attributes": [
        {**_STRING_ATTR, "name": "displayName", "required": True},
        {
            "name": "members",
            "type": "complex",
            "multiValued": True,
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
            "subAttributes": [{**_STRING_ATTR, "name": "value"}],
        },
    ],
    "meta": {"resourceType": "Schema", "location": f"/scim/v2/Schemas/{GROUP_SCHEMA}"},
}

SCHEMAS_BY_ID: dict[str, dict[str, Any]] = {
    USER_SCHEMA: USER_SCHEMA_DEF,
    GROUP_SCHEMA: GROUP_SCHEMA_DEF,
}
