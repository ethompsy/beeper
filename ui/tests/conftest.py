"""Pytest fixtures for Beeper UI tests."""

from collections.abc import Generator

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

    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.get(*args, headers=headers, **kwargs)

    def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.post(*args, headers=headers, **kwargs)

    def put(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.put(*args, headers=headers, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
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
