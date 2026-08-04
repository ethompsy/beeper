"""Smoke tests for Task 1.1: Flask serving of the React build bundle.

Acceptance criterion [T]:
  "The UI Docker image builds the bundle via the Node stage and serves
   index.html + hashed assets. Prove with a smoke test asserting the Flask
   app returns the built index.html at its mount path and serves a hashed
   asset with a 200."

Because a full docker build is slow / may not be available in CI, we verify
the *serving half* against a real local `npm run build` output (Flask serving
dist/) and document the Docker wiring inspection separately in the task summary.

These tests require that  ui/frontend/dist/  already exists (produced by
`npm run build` in ui/frontend/).  If the dist is absent, tests are skipped
with an informative message.
"""

import os
import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

# Locate the frontend dist directory relative to this file.
# This file:  ui/tests/test_react_shell.py
# dist:       ui/frontend/dist/
_TESTS_DIR = Path(__file__).parent
_DIST = _TESTS_DIR.parent / "frontend" / "dist"

_DIST_MISSING_REASON = (
    f"frontend dist not built: run `npm run build` in ui/frontend/ first. "
    f"(looked for {_DIST})"
)


def _dist_available() -> bool:
    return (_DIST / "index.html").is_file()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def react_client(app: Flask) -> FlaskClient:
    """Return a Flask test client with the React shell blueprint active."""
    return app.test_client()


# ── helper ───────────────────────────────────────────────────────────────────


def _find_hashed_asset(prefix: str = "index", ext: str = "js") -> str | None:
    """Find the first hashed asset matching <prefix>-<hash>.<ext> in dist/assets/."""
    assets = _DIST / "assets"
    if not assets.is_dir():
        return None
    # Vite emits base64url content hashes, which may contain '-' and '_' (e.g. index-CipiD-gB.js)
    pattern = re.compile(rf"^{re.escape(prefix)}-[A-Za-z0-9_-]{{8,}}\.{re.escape(ext)}$")
    for name in os.listdir(assets):
        if pattern.match(name):
            return name
    return None


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
def test_react_shell_root_returns_index_html(react_client: FlaskClient) -> None:
    """GET /app/ returns 200 and the React index.html content."""
    response = react_client.get("/app/")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.get_data(as_text=True)
    # Vite index.html always has a <div id="root"> and references the JS entry
    assert "<div id=" in data or "<script" in data, (
        "Response does not look like an HTML SPA shell"
    )


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
def test_react_shell_subpath_returns_index_html(react_client: FlaskClient) -> None:
    """GET /app/investigations returns 200 + index.html (client-side routing)."""
    response = react_client.get("/app/investigations")
    assert response.status_code == 200
    data = response.get_data(as_text=True)
    assert "<!doctype html>" in data.lower() or "<html" in data.lower()


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
def test_react_shell_serves_hashed_js_asset(react_client: FlaskClient) -> None:
    """GET /app/assets/<hashed>.js returns 200 with correct content-type."""
    asset_name = _find_hashed_asset("index", "js")
    assert asset_name is not None, (
        f"No hashed index-*.js found in {_DIST / 'assets'} — "
        "run `npm run build` in ui/frontend/"
    )
    response = react_client.get(f"/app/assets/{asset_name}")
    assert response.status_code == 200, (
        f"Expected 200 for /app/assets/{asset_name}, got {response.status_code}"
    )
    ct = response.content_type
    assert "javascript" in ct or "application/octet-stream" in ct, (
        f"Unexpected content-type for JS asset: {ct}"
    )


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
def test_react_shell_serves_hashed_css_asset(react_client: FlaskClient) -> None:
    """GET /app/assets/<hashed>.css returns 200 with css content-type."""
    asset_name = _find_hashed_asset("index", "css")
    assert asset_name is not None, (
        f"No hashed index-*.css found in {_DIST / 'assets'} — "
        "run `npm run build` in ui/frontend/"
    )
    response = react_client.get(f"/app/assets/{asset_name}")
    assert response.status_code == 200, (
        f"Expected 200 for /app/assets/{asset_name}, got {response.status_code}"
    )
    ct = response.content_type
    assert "css" in ct, f"Unexpected content-type for CSS asset: {ct}"


@pytest.mark.skipif(not _dist_available(), reason=_DIST_MISSING_REASON)
def test_react_shell_does_not_shadow_existing_jinja_routes(
    react_client: FlaskClient,
) -> None:
    """Existing Jinja routes outside /app/ are unaffected by the React blueprint.

    /health/api is a lightweight JSON endpoint that doesn't need an operator
    connection — verifies that the React blueprint (mounted at /app) does not
    shadow existing routes.
    """
    response = react_client.get("/health/api")
    # If health/api returns anything other than 404 the route is still reachable.
    # (It may 500 if the operator is unreachable — that's fine for isolation.)
    assert response.status_code != 404, (
        "/health/api disappeared — React blueprint may be shadowing existing routes"
    )
