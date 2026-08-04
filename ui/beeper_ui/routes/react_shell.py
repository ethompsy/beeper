"""React SPA shell serving routes.

Task 1.1: minimal, non-conflicting routes that serve the pre-built Vite
bundle (`ui/frontend/dist/`) as static assets plus the SPA `index.html`
at a dedicated mount prefix (`/app`).

Scope: scaffold + build wiring only.  The full React-vs-Jinja route-dispatch
registry is Task 1.3 — these routes are intentionally minimal and do NOT
touch existing Jinja blueprints.

Directory layout (relative to the Flask app root, i.e. /app inside Docker):
    frontend/dist/index.html          -- SPA shell
    frontend/dist/assets/<hashed>.*   -- JS/CSS/image assets

In development (local Flask without Docker) the dist/ lives at:
    ui/frontend/dist/  (sibling of beeper_ui/)
In Docker (multi-stage build) it is copied to:
    /app/frontend/dist/  (sibling of /app/beeper_ui/)

The blueprint resolves the dist path relative to this file at import time so
it works in both environments without environment variables.
"""

from pathlib import Path

from flask import Blueprint, send_file, send_from_directory

# Resolve frontend/dist relative to this source file.
# This file lives at  beeper_ui/routes/react_shell.py
# dist lives at       frontend/dist/  (one level up from beeper_ui, then into frontend/)
_ROUTES_DIR = Path(__file__).parent          # beeper_ui/routes/
_BEEPER_UI_DIR = _ROUTES_DIR.parent          # beeper_ui/
_APP_ROOT = _BEEPER_UI_DIR.parent            # ui/  (or /app in Docker)
REACT_DIST = _APP_ROOT / "frontend" / "dist"

react_shell_bp = Blueprint(
    "react_shell",
    __name__,
    # No static_folder here — we serve manually for full control over caching headers.
    url_prefix="/app",
)


@react_shell_bp.route("/", defaults={"path": ""})
@react_shell_bp.route("/<path:path>")
def serve_react_shell(path: str) -> object:
    """Serve the React SPA shell at /app/*.

    - Hashed asset files (js/css/images inside assets/) are served directly.
    - All other paths within /app/* return index.html so React Router can
      handle client-side navigation.

    This blueprint intentionally does NOT intercept /api/*, /health, or any
    other existing Jinja blueprint prefixes — those are registered normally.
    """
    # Try to serve an exact static asset first (e.g. /app/assets/index-abc123.js)
    candidate = REACT_DIST / path
    if path and candidate.is_file():
        return send_from_directory(str(REACT_DIST), path)

    # Everything else → SPA shell (React Router handles the rest)
    return send_file(str(REACT_DIST / "index.html"))
