"""React-owned path-prefix dispatch registry (Task 1.3 / D11).

Problem
-------
The BFF hosts 18+ Jinja blueprints today and will migrate views to React
incrementally (Milestone 1.2 onward). Some URLs — e.g. ``/investigations`` —
exist in *both* worlds during the migration window. Flask's URL map doesn't
give us a reliable way to make "React wins for this prefix" an explicit,
order-independent decision: whichever blueprint happens to own the more
specific rule wins, and that depends on registration order and Werkzeug's
matching rules, not on migration intent.

Design (D11)
------------
We maintain an explicit, ordered list of React-owned path prefixes
(``REACT_OWNED_PREFIXES``). A ``before_request`` hook checks every incoming
request path against that registry *before* Flask's normal view dispatch
runs:

- If the path matches a registered React-owned prefix, we short-circuit
  straight to the React shell (``serve_react_shell``), regardless of
  whether a Jinja blueprint also claims that path. This makes precedence
  deterministic and independent of blueprint registration order.
- ``/api/*`` and the SSE/JSON-event endpoints are always excluded from the
  registry match, even if a caller mistakenly registers a prefix that would
  overlap them — the JSON API (Task 1.6) and streaming endpoints must never
  be shadowed by the SPA shell.
- The React shell's own mount (``/app``) continues to be served directly by
  its blueprint and is not part of this registry (it has no Jinja
  equivalent to race against).
- If the path matches no registered prefix, ``before_request`` returns
  ``None`` and Flask proceeds with normal dispatch (Jinja blueprints, the
  JSON API, health checks, etc.) exactly as before this task.

Registry starts **empty** in production defaults — Task 1.3 only builds the
mechanism. Real view migrations (e.g. ``/investigations``) happen in
Milestone 1.2 by appending to this list (or the ``REACT_OWNED_PREFIXES``
Flask config key).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flask import Flask, current_app, request

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

# Prefixes that must never be claimed by the React registry, even if a caller
# accidentally registers an overlapping prefix. Checked first, unconditionally.
_ALWAYS_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/app/",  # the React shell's own static/asset mount — served by its blueprint
)

# Default registry: empty. Populate via app.config["REACT_OWNED_PREFIXES"]
# (falls back to this default when the key is absent) as views are migrated.
DEFAULT_REACT_OWNED_PREFIXES: tuple[str, ...] = ()


def _is_always_excluded(path: str) -> bool:
    """Return True if `path` falls under a permanently-excluded prefix."""
    return any(
        path == excluded.rstrip("/") or path.startswith(excluded)
        for excluded in _ALWAYS_EXCLUDED_PREFIXES
    )


def _normalize_prefix(prefix: str) -> str:
    """Normalize a registry entry to a bare '/segment' form (no trailing slash)."""
    prefix = prefix.strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix.rstrip("/") or "/"


def matches_react_prefix(path: str, prefixes: tuple[str, ...] | list[str]) -> bool:
    """Return True if `path` falls under one of the given React-owned prefixes.

    A path matches a prefix if it equals the prefix exactly or starts with
    "<prefix>/" — this mirrors Flask's own `url_prefix` semantics so that
    e.g. prefix "/investigations" matches "/investigations" and
    "/investigations/abc123" but not "/investigations-other".
    """
    if _is_always_excluded(path):
        return False
    for raw_prefix in prefixes:
        prefix = _normalize_prefix(raw_prefix)
        if prefix == "/":
            # A registered root prefix matches everything except exclusions.
            return True
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def get_react_owned_prefixes(app: Flask) -> tuple[str, ...]:
    """Read the active registry from Flask config, falling back to the default."""
    configured = app.config.get("REACT_OWNED_PREFIXES")
    if configured is None:
        return DEFAULT_REACT_OWNED_PREFIXES
    return tuple(configured)


def init_react_dispatch(app: Flask) -> None:
    """Install the before_request hook implementing deterministic dispatch.

    Must be called after `react_shell_bp` is registered (so its view function
    is importable), but works correctly regardless of *when* other Jinja
    blueprints are registered relative to this call — the hook intercepts
    before Flask's URL-map dispatch ever runs.
    """
    from beeper_ui.routes.react_shell import serve_react_shell

    @app.before_request
    def _dispatch_react_owned_paths() -> ResponseReturnValue | None:
        path = request.path
        prefixes = get_react_owned_prefixes(current_app)
        if not matches_react_prefix(path, prefixes):
            return None
        # Strip the leading slash to match serve_react_shell's <path:path> arg shape.
        # serve_react_shell is annotated `-> object` (Task 1.1); it actually
        # always returns a Flask-compatible response (send_file/send_from_directory).
        return cast("ResponseReturnValue", serve_react_shell(path.lstrip("/")))
