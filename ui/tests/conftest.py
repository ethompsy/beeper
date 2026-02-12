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
