"""Pytest fixtures for Beeper UI tests."""

from collections.abc import Generator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create application for testing."""
    app = create_app(TestingConfig)
    yield app


@pytest.fixture
def client(app: Flask) -> Generator[FlaskClient, None, None]:
    """Create test client."""
    with app.test_client() as test_client:
        yield test_client


class _RoleClient:
    """Wrapper that injects X-Beeper-Role header on every request."""

    def __init__(self, client: FlaskClient, role: str) -> None:
        self._client = client
        self._role = role

    def get(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.get(*args, headers=headers, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.post(*args, headers=headers, **kwargs)

    def put(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.put(*args, headers=headers, **kwargs)

    def patch(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.patch(*args, headers=headers, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.delete(*args, headers=headers, **kwargs)


@pytest.fixture
def admin_client(app: Flask) -> Generator[_RoleClient, None, None]:
    """Create test client with admin role."""
    with app.test_client() as test_client:
        yield _RoleClient(test_client, "admin")


@pytest.fixture
def user_client(app: Flask) -> Generator[_RoleClient, None, None]:
    """Create test client with user role."""
    with app.test_client() as test_client:
        yield _RoleClient(test_client, "user")


@pytest.fixture(autouse=True)
def _reset_identity_store_between_tests() -> Generator[None, None, None]:
    """Reset the identity-store singleton after every test (merge resolution,
    Tasks 8.3 x 8.6).

    Task 8.6 made `create_app()` in `local` mode initialize the store
    singleton as a boot side effect (bootstrap -> refresh_zero_admin_alarm),
    so test files that merely build a local-mode app leak the singleton
    process-globally without ever importing it. The leaked store then makes
    `/health/api` grow its `zero_active_admins` flag in unrelated mode-`none`
    tests (exact-body assertions fail). Store-using test files already reset
    locally; this autouse teardown kills the whole leak class.
    """
    yield
    from beeper_ui.services.identity_store import reset_identity_store

    reset_identity_store()
