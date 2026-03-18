"""Tests for command palette and keyboard shortcuts."""

import os

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture
def app() -> Flask:
    """Create test application."""
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client."""
    with app.test_client() as test_client:
        yield test_client


class TestCommandPaletteInclusion:
    """Test that command palette is included in base template."""

    def test_base_template_includes_command_palette_overlay(
        self, client: FlaskClient
    ) -> None:
        """Base template should include the command palette overlay div."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.data.decode()
        assert 'id="command-palette-overlay"' in html

    def test_base_template_includes_keyboard_help_overlay(
        self, client: FlaskClient
    ) -> None:
        """Base template should include the keyboard help overlay div."""
        response = client.get("/")
        html = response.data.decode()
        assert 'id="keyboard-help-overlay"' in html

    def test_base_template_includes_command_palette_js(
        self, client: FlaskClient
    ) -> None:
        """Base template should load the command-palette.js script."""
        response = client.get("/")
        html = response.data.decode()
        assert "command-palette.js" in html


class TestCommandPaletteTemplate:
    """Test command palette template ARIA attributes."""

    def test_command_palette_has_aria_combobox(self, app: Flask) -> None:
        """Command palette search input should have role=combobox."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'role="combobox"' in html

    def test_command_palette_has_aria_owns(self, app: Flask) -> None:
        """Search input should reference results list via aria-owns."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'aria-owns="command-results"' in html

    def test_command_palette_has_aria_autocomplete(self, app: Flask) -> None:
        """Search input should have aria-autocomplete=list."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'aria-autocomplete="list"' in html

    def test_command_palette_has_aria_label(self, app: Flask) -> None:
        """Search input should have a descriptive aria-label."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'aria-label="Search commands and navigation"' in html

    def test_command_palette_has_aria_expanded(self, app: Flask) -> None:
        """Search input should start with aria-expanded=false."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'aria-expanded="false"' in html

    def test_command_palette_has_results_listbox(self, app: Flask) -> None:
        """Results list should have role=listbox."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert 'role="listbox"' in html

    def test_command_palette_overlay_hidden_by_default(
        self, app: Flask
    ) -> None:
        """Overlay should not have 'active' class by default."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_command_palette.html"
            )
            html = template.render()
            assert "command-palette-overlay" in html
            assert "active" not in html.split("command-palette-overlay")[1].split('"')[0]


class TestKeyboardHelpTemplate:
    """Test keyboard help overlay template."""

    def test_keyboard_help_contains_cmd_k_shortcut(self, app: Flask) -> None:
        """Help overlay should show Cmd+K shortcut."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "Cmd" in html
            assert "Open command palette" in html

    def test_keyboard_help_contains_navigation_shortcuts(
        self, app: Flask
    ) -> None:
        """Help overlay should list navigation chord shortcuts."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "Go to Investigations" in html
            assert "Go to SLO Dashboard" in html
            assert "Go to Knowledge Base" in html
            assert "Go to Notifications" in html
            assert "Go to Topology" in html
            assert "Go to Health" in html
            assert "Go to Metrics" in html

    def test_keyboard_help_contains_investigation_shortcuts(
        self, app: Flask
    ) -> None:
        """Help overlay should reference investigation actions."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "Annotate" in html
            assert "Redirect" in html
            assert "Approve" in html
            assert "Reject" in html

    def test_keyboard_help_contains_help_shortcut(self, app: Flask) -> None:
        """Help overlay should show the ? shortcut."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "Toggle this help" in html

    def test_keyboard_help_has_close_button(self, app: Flask) -> None:
        """Help overlay should have a close button."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "keyboard-help-close" in html
            assert 'aria-label="Close keyboard shortcuts help"' in html

    def test_keyboard_help_overlay_hidden_by_default(
        self, app: Flask
    ) -> None:
        """Help overlay should not have 'active' class by default."""
        with app.app_context():
            template = app.jinja_env.get_template(
                "components/_keyboard_help.html"
            )
            html = template.render()
            assert "keyboard-help-overlay" in html
            assert "active" not in html.split("keyboard-help-overlay")[1].split('"')[0]


class TestCommandPaletteStaticFiles:
    """Test that command palette static files exist."""

    def test_command_palette_js_exists(self) -> None:
        """command-palette.js should exist in static/js."""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "js",
            "command-palette.js",
        )
        assert os.path.isfile(js_path), f"Missing: {js_path}"

    def test_command_palette_js_has_commands_array(self) -> None:
        """command-palette.js should define a COMMANDS array."""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "js",
            "command-palette.js",
        )
        with open(js_path) as f:
            content = f.read()
        assert "COMMANDS" in content
        assert "/investigations/" in content
        assert "/slo/" in content
        assert "/knowledge/" in content

    def test_command_palette_js_has_chord_shortcuts(self) -> None:
        """command-palette.js should define chord shortcuts."""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "js",
            "command-palette.js",
        )
        with open(js_path) as f:
            content = f.read()
        assert "CHORD_SHORTCUTS" in content
        assert "pendingKey" in content

    def test_command_palette_js_has_aria_support(self) -> None:
        """command-palette.js should manage ARIA attributes."""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "js",
            "command-palette.js",
        )
        with open(js_path) as f:
            content = f.read()
        assert "aria-expanded" in content
        assert "aria-selected" in content
        assert "aria-activedescendant" in content


class TestCommandPaletteCSSIntegration:
    """Test that command palette CSS styles are included."""

    def test_main_css_has_command_palette_styles(self) -> None:
        """main.css should include command palette overlay styles."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "css",
            "main.css",
        )
        with open(css_path) as f:
            content = f.read()
        assert ".command-palette-overlay" in content
        assert ".command-palette" in content
        assert ".command-result-item" in content
        assert ".command-shortcut-badge" in content

    def test_main_css_has_keyboard_help_styles(self) -> None:
        """main.css should include keyboard help overlay styles."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "css",
            "main.css",
        )
        with open(css_path) as f:
            content = f.read()
        assert ".keyboard-help-overlay" in content
        assert ".keyboard-help" in content

    def test_main_css_has_reduced_motion_support(self) -> None:
        """main.css should have prefers-reduced-motion media query."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "static",
            "css",
            "main.css",
        )
        with open(css_path) as f:
            content = f.read()
        assert "prefers-reduced-motion" in content
