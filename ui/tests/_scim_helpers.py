"""Shared config classes/builders for SCIM surface tests (Task 8.8).

Not a test file itself (no `test_` prefix — mirrors `tests/_fake_qdrant.py`'s
convention; not collected by pytest). Every `test_scim_*.py` file builds its
own Flask app via `build_scim_app()` rather than reusing the top-level
`tests/conftest.py` `app`/`client` fixtures, which default to
`BEEPER_AUTH_MODE=none` (SCIM is never registered there) — this mirrors the
pattern `tests/test_identity_resolver.py` already established for
`local`/`oidc` config variants (custom `TestingConfig` subclasses + a local
`_make_app()`-style builder, not a shared fixture override).

Each test file is expected to define its own small, LOCAL
`@pytest.fixture(autouse=True)` for `SECRET_KEY` env + store-singleton
reset, exactly like `test_identity_resolver.py` does — kept per-file
(not centralized here) to match that established convention rather than
relying on cross-module autouse-fixture-import behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.identity_store import IdentityStoreService, set_identity_store_for_testing
from tests._fake_qdrant import FakeQdrantClient

SCIM_TOKEN = "test-scim-primary-token-0123456789"
SCIM_TOKEN_SECONDARY = "test-scim-secondary-token-9876543210"


class ScimTestConfig(TestingConfig):
    """SCIM enabled, single (primary) token configured."""

    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = True
    BEEPER_SCIM_TOKEN = SCIM_TOKEN
    BEEPER_SCIM_TOKEN_SECONDARY = ""
    # Task 8.5's boot refusal requires OIDC completeness in `oidc` mode
    # (merge-resolution addition, same stubs as test_auth_me.py).
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


class ScimDualTokenConfig(ScimTestConfig):
    """Both primary and secondary tokens configured — rotation window."""

    BEEPER_SCIM_TOKEN_SECONDARY = SCIM_TOKEN_SECONDARY


class ScimTokenlessConfig(ScimTestConfig):
    """SCIM enabled, but neither token configured — the ADR §8
    "enabled but unconfigured" fail-closed-403 case."""

    BEEPER_SCIM_TOKEN = ""
    BEEPER_SCIM_TOKEN_SECONDARY = ""


class ScimStrictConfig(ScimTestConfig):
    BEEPER_SCIM_STRICT = True


class ScimDisabledConfig(TestingConfig):
    """SCIM disabled — the blueprint must not be registered at all."""

    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = False
    # Task 8.5 boot-refusal stubs (merge-resolution addition).
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


def auth_headers(token: str = SCIM_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class ManualClock:
    """A controllable monotonic clock for deterministic TTL-cache tests
    (same shape as `tests/test_identity_store.py::_ManualClock`)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build_scim_app(
    config_class: type = ScimTestConfig,
    *,
    admin_groups: tuple[str, ...] = ("Admins", "beeper-admin"),
    clock: Any = None,
) -> tuple[Flask, IdentityStoreService, FakeQdrantClient]:
    """Build a Flask app with a fresh `FakeQdrantClient`-backed
    `IdentityStoreService` pre-installed as the module singleton BEFORE
    `create_app()` runs. Callers are responsible for their own
    `reset_identity_store()` before/after (via a local autouse fixture —
    see module docstring) and for setting `SECRET_KEY` in the process
    environment (`local`/`oidc` boot validation requires it, ADR §2/§8).
    """
    fake_client = FakeQdrantClient()
    with patch("beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client):
        kwargs: dict[str, Any] = {"admin_groups": admin_groups}
        if clock is not None:
            kwargs["clock"] = clock
        store = IdentityStoreService(**kwargs)
    set_identity_store_for_testing(store)
    app = create_app(config_class)
    return app, store, fake_client


def make_client(app: Flask) -> FlaskClient:
    return app.test_client()
