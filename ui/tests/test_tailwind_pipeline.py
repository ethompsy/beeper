"""Tests for Tailwind CSS build pipeline (Story 3.1)."""

import pathlib

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig

_UI_ROOT = pathlib.Path(__file__).parent.parent
_STATIC_CSS = _UI_ROOT / "beeper_ui" / "static" / "css"


@pytest.fixture
def app() -> Flask:
    """Create test application."""
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client."""
    with app.test_client() as c:
        yield c


class TestTailwindBaseTemplate:
    """Verify base.html includes both tailwind.css and main.css."""

    def test_tailwind_css_link_present(self, client: FlaskClient) -> None:
        """base.html must include the tailwind.css stylesheet."""
        response = client.get("/")
        assert b"css/tailwind.css" in response.data

    def test_main_css_link_still_present(self, client: FlaskClient) -> None:
        """base.html must still include the main.css stylesheet."""
        response = client.get("/")
        assert b"css/main.css" in response.data

    def test_tailwind_loaded_before_main(self, client: FlaskClient) -> None:
        """tailwind.css must load before main.css for specificity."""
        html = client.get("/").data.decode()
        tw_pos = html.index("css/tailwind.css")
        main_pos = html.index("css/main.css")
        assert tw_pos < main_pos


class TestTailwindInputFile:
    """Verify input.css source file exists with expected content."""

    def test_input_css_exists(self) -> None:
        """input.css source file must exist."""
        assert (_STATIC_CSS / "input.css").is_file()

    def test_input_css_imports_tailwind_theme(self) -> None:
        """input.css must import tailwindcss theme layer."""
        content = (_STATIC_CSS / "input.css").read_text()
        assert "tailwindcss/theme.css" in content

    def test_input_css_imports_tailwind_utilities(self) -> None:
        """input.css must import tailwindcss utilities layer."""
        content = (_STATIC_CSS / "input.css").read_text()
        assert "tailwindcss/utilities.css" in content

    def test_input_css_does_not_import_preflight(self) -> None:
        """input.css must NOT import preflight (would break existing CSS)."""
        content = (_STATIC_CSS / "input.css").read_text()
        assert "tailwindcss/preflight.css" not in content

    def test_input_css_contains_design_tokens(self) -> None:
        """input.css must define all v0.2.0 design tokens."""
        content = (_STATIC_CSS / "input.css").read_text()
        expected_tokens = [
            "--color-surface-base",
            "--color-surface-raised",
            "--color-surface-overlay",
            "--color-primary:",
            "--color-primary-hover",
            "--color-status-healthy",
            "--color-status-warning",
            "--color-status-critical",
            "--color-status-muted",
            "--color-text-primary",
            "--color-text-secondary",
            "--color-text-muted",
        ]
        for token in expected_tokens:
            assert token in content, f"Missing design token: {token}"

    def test_input_css_contains_breakpoints(self) -> None:
        """input.css must define custom breakpoints."""
        content = (_STATIC_CSS / "input.css").read_text()
        assert "--breakpoint-sm: 768px" in content
        assert "--breakpoint-lg: 1200px" in content
        assert "--breakpoint-xl: 1920px" in content
