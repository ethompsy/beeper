"""Hand-authored JSON Schemas (Draft 2020-12) used as a conformance oracle
for the SCIM 2.0 response shapes this surface emits — RFC 7643 §§3-4, 8 and
RFC 7644 §3.4.2/§3.12 don't publish official JSON Schema files, so these
capture the attributes this codebase actually promises (and the tests
actually exercise), not an exhaustive transcription of every optional RFC
attribute.

Not a test file itself (no `test_` prefix). `jsonschema` is a dev-only
dependency (ADR 0002 §4: "JSON-Schema response validation is a
dev-dependency only") — see `ui/pyproject.toml`.
"""

from __future__ import annotations

from typing import Any

USER_RESOURCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemas", "id", "userName", "active", "meta"],
    "properties": {
        "schemas": {
            "type": "array",
            "items": {"const": "urn:ietf:params:scim:schemas:core:2.0:User"},
        },
        "id": {"type": "string", "minLength": 1},
        "externalId": {"type": ["string", "null"]},
        "userName": {"type": "string", "minLength": 1},
        "displayName": {"type": "string"},
        "name": {
            "type": "object",
            "properties": {"formatted": {"type": "string"}},
        },
        "emails": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}, "primary": {"type": "boolean"}},
            },
        },
        "active": {"type": "boolean"},
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
            },
        },
        "meta": {
            "type": "object",
            "required": ["resourceType", "location"],
            "properties": {
                "resourceType": {"const": "User"},
                "created": {"type": "string"},
                "lastModified": {"type": "string"},
                "location": {"type": "string"},
            },
        },
    },
}

GROUP_RESOURCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemas", "id", "displayName", "meta"],
    "properties": {
        "schemas": {
            "type": "array",
            "items": {"const": "urn:ietf:params:scim:schemas:core:2.0:Group"},
        },
        "id": {"type": "string", "minLength": 1},
        "externalId": {"type": ["string", "null"]},
        "displayName": {"type": "string", "minLength": 1},
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
            },
        },
        "meta": {
            "type": "object",
            "required": ["resourceType", "location"],
            "properties": {
                "resourceType": {"const": "Group"},
                "location": {"type": "string"},
            },
        },
    },
}


def list_response_schema(item_schema: dict[str, Any]) -> dict[str, Any]:
    """RFC 7644 §3.4.2 ListResponse envelope, parameterized over the
    contained resource's own schema."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["schemas", "totalResults", "startIndex", "itemsPerPage", "Resources"],
        "properties": {
            "schemas": {
                "type": "array",
                "items": {"const": "urn:ietf:params:scim:api:messages:2.0:ListResponse"},
            },
            "totalResults": {"type": "integer", "minimum": 0},
            "startIndex": {"type": "integer", "minimum": 1},
            "itemsPerPage": {"type": "integer", "minimum": 0},
            "Resources": {"type": "array", "items": item_schema},
        },
    }


SCIM_ERROR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemas", "status", "detail"],
    "properties": {
        "schemas": {
            "type": "array",
            "items": {"const": "urn:ietf:params:scim:api:messages:2.0:Error"},
        },
        "status": {"type": "string"},
        "detail": {"type": "string"},
        "scimType": {"type": "string"},
    },
}

SERVICE_PROVIDER_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemas", "patch", "filter", "authenticationSchemes"],
    "properties": {
        "schemas": {
            "type": "array",
            "items": {
                "const": "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
            },
        },
        "patch": {"type": "object", "required": ["supported"]},
        "filter": {"type": "object", "required": ["supported", "maxResults"]},
        "authenticationSchemes": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "object", "required": ["type", "name"]},
        },
    },
}

RESOURCE_TYPE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemas", "id", "name", "endpoint", "schema"],
    "properties": {
        "schemas": {
            "type": "array",
            "items": {"const": "urn:ietf:params:scim:schemas:core:2.0:ResourceType"},
        },
        "id": {"type": "string"},
        "name": {"type": "string"},
        "endpoint": {"type": "string"},
        "schema": {"type": "string"},
    },
}

SCHEMA_DEFINITION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "name", "attributes"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "attributes": {"type": "array", "items": {"type": "object", "required": ["name", "type"]}},
    },
}
