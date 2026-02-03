"""Tests for Beeper UI Flask application."""

from collections.abc import Generator

import pytest
from flask.testing import FlaskClient

from beeper_ui import __version__
from beeper_ui.app import app


@pytest.fixture
def client() -> Generator[FlaskClient, None, None]:
    """Create test client."""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_version() -> None:
    """Test version is set."""
    assert __version__ == "0.1.0"


def test_health_endpoint(client) -> None:
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "healthy"}


def test_index_page(client) -> None:
    """Test index page renders."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Beeper" in response.data
