"""Shared fixtures for demo application tests."""

import os
import sys

import pytest

# Ensure the demo app module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from server import create_app  # noqa: E402


@pytest.fixture(params=["api-gateway", "backend", "database", "worker"])
def role(request):
    """Parameterized fixture providing each service role."""
    return request.param


@pytest.fixture()
def app(role):
    """Create a Flask test app for the given role."""
    application = create_app(role=role)
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture()
def api_gateway_client():
    """Create a test client for the api-gateway role."""
    application = create_app(role="api-gateway")
    application.config["TESTING"] = True
    return application.test_client()


@pytest.fixture()
def backend_client():
    """Create a test client for the backend role."""
    application = create_app(role="backend")
    application.config["TESTING"] = True
    return application.test_client()


@pytest.fixture()
def database_client():
    """Create a test client for the database role."""
    application = create_app(role="database")
    application.config["TESTING"] = True
    return application.test_client()


@pytest.fixture()
def worker_client():
    """Create a test client for the worker role."""
    application = create_app(role="worker")
    application.config["TESTING"] = True
    return application.test_client()
