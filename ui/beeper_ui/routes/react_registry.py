"""React-owned path-prefix dispatch registry (Task 1.3 / D11; redirect
cutover Task 6.3 / D13-D14).

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

- If the path matches a registered React-owned prefix (and isn't carved out
  — see "Cutover redirect" below), the request never reaches Flask's normal
  dispatch. This makes precedence deterministic and independent of blueprint
  registration order.
- ``/api/*`` and the SSE/JSON-event endpoints are always excluded from the
  registry match, even if a caller mistakenly registers a prefix that would
  overlap them — the JSON API (Task 1.6) and streaming endpoints must never
  be shadowed.
- The React shell's own mount (``/app``) continues to be served directly by
  its blueprint and is not part of this registry (it has no Jinja
  equivalent to race against).
- If the path matches no registered prefix, ``before_request`` returns
  ``None`` and Flask proceeds with normal dispatch (Jinja blueprints, the
  JSON API, health checks, etc.) exactly as before this task.

Registry starts **empty** in production defaults — Task 1.3 only builds the
mechanism. Real view migrations (e.g. ``/investigations``) happen by
appending to this list (or the ``REACT_OWNED_PREFIXES`` Flask config key).

Cutover redirect (D14 / Task 6.3)
----------------------------------
Originally (Task 1.3-5.4) a matched path was served the React shell *in
place*, at the original bare URL. That never actually worked end-to-end for
a bare (non-``/app``) path: the built bundle's assets use Vite
``base: '/app/'`` and React Router's ``basename: '/app'`` (``App.tsx``), so
the shell rendered at e.g. ``/knowledge`` has no route to match against and
renders a blank/`Page not found` shell (see Q9's original finding).

D14 resolves this: a matched, non-excluded path now 302-redirects to its
``/app/*`` equivalent instead of being served in place. This is the "narrow
cutover" (D13) — only the six migrated destinations
(``/investigations``, ``/knowledge``, ``/health/ingestion``, ``/sources``,
``/spending``, ``/metrics``) are registered; the ten un-migrated nav
destinations documented in
``docs/design/route-parity-targets.md`` §7 are never added to this registry
and keep rendering Jinja untouched.

Two extra pieces of bookkeeping the redirect needs that plain prefix
membership does not:

1. **Exclusions** (`_REDIRECT_EXCLUSION_PATTERNS`) — sub-routes that live
   *underneath* a registered prefix but were never migrated (route-parity-
   targets.md §2 KB write/history/admin carve-outs, §4b Cost Insights, §5
   `/metrics/export`) or are Jinja-only investigation actions/streams the
   React detail view never called (kept deliberately — see Task 6.3
   report). A path matching an exclusion pattern is dispatched normally
   even though it falls under a registered prefix.
2. **Target overrides** (`_REDIRECT_TARGET_OVERRIDES`) — a handful of bare
   paths whose React destination is not simply ``"/app" + path``: Ingestion
   Stats lives at a differently-named React route, and a few HTMX-only
   auto-refresh/search partials collapse into the *same* React view as
   their parent page (search is a ``?q=`` query param on ``/app/knowledge``,
   not its own path; the MTTR partial + drilldown are the same
   ``/app/metrics`` view; the spending status partial is the same
   ``/app/spending`` view).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from flask import Flask, current_app, redirect, request

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

# ---------------------------------------------------------------------------
# Task 6.3 cutover: redirect exclusions + target overrides
# ---------------------------------------------------------------------------

# Sub-routes that fall *under* a registered React-owned prefix but must NOT
# redirect. Checked after prefix membership; a match here always wins even
# though the path is nested under a registered prefix — see the module
# docstring's "Cutover redirect" section for the reasoning behind each
# group.
_REDIRECT_EXCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Investigations: the per-investigation HTMX action routes (verify,
    # confirm, reject, resolve, one-click feedback, related/linked KB,
    # confidence-gate, urgency, remediation-progress) and both HTML SSE
    # streams were never called by React (the Phase-1 detail view consumes
    # the JSON API/SSE at /api/v1/investigations/*, not these) and are not
    # part of the "migrated" set (D13) — only the list/detail full pages
    # are retired. Excluding them keeps these Jinja-only, some
    # `require_role`-gated, routes reachable and tested rather than
    # silently 302'd to a nonexistent /app path.
    re.compile(
        r"^/investigations/[^/]+/(?:verify|confirm|reject|resolve|feedback"
        r"|related-kb|linked-kb|gate-status|urgency|remediation-progress"
        r"|stream)$"
    ),
    # Knowledge: every write/history/admin sub-route (import, preview,
    # learning*, trust-settings*, per-service knowledge, the investigator
    # prompt-context API, and every per-entry edit/confirm/history/related/
    # version/diff/restore/corrections* route) is an explicit route-parity-
    # targets.md §2 carve-out — never migrated, must keep rendering.
    re.compile(
        r"^/knowledge/(?:import|preview|learning|trust-settings|services|api)"
        r"(?:/.*)?$"
    ),
    re.compile(
        r"^/knowledge/[^/]+/(?:edit|confirm|history|related|version|diff"
        r"|restore|corrections)(?:/.*)?$"
    ),
    # Spending: Cost Insights (`/spending/costs*`) is a separate,
    # un-migrated nav destination (route-parity-targets.md §7) that happens
    # to share the `/spending` prefix with the retired dashboard.
    re.compile(r"^/spending/costs(?:/.*)?$"),
    # Metrics: the CSV/JSON export endpoint has no template of its own and
    # the React Metrics view links to it directly (route-parity-targets.md
    # §5) — must survive untouched.
    re.compile(r"^/metrics/export$"),
)

# Bare Jinja paths whose React destination is NOT a plain "/app" + path
# rewrite. See the module docstring's "target overrides" paragraph.
_REDIRECT_TARGET_OVERRIDES: dict[str, str] = {
    "/health/ingestion": "/app/ingestion-stats",
    "/knowledge/search": "/app/knowledge",
    "/metrics/mttr": "/app/metrics",
    "/metrics/mttr/drilldown": "/app/metrics",
    "/spending/status": "/app/spending",
}


def _is_redirect_excluded(path: str) -> bool:
    """Return True if `path` is a deliberate carve-out (see module docstring)."""
    return any(pattern.match(path) for pattern in _REDIRECT_EXCLUSION_PATTERNS)


def build_app_redirect_target(path: str) -> str:
    """Compute the `/app/*` redirect target for a React-owned bare path.

    Preserves the query string — FR53 permalinks (`?q=`, `?status=`,
    `?period=`, etc.) must survive the hop. Fragments need no handling
    here: per the Fetch/HTML redirect algorithm, a browser propagates the
    original request URL's fragment onto a `Location` header that doesn't
    specify one of its own, so `#step-3` on `/investigations/x#step-3`
    survives automatically — fragments are never even sent to the server.
    """
    base = _REDIRECT_TARGET_OVERRIDES.get(path)
    if base is None:
        stripped = path.rstrip("/")
        base = "/app" if not stripped else f"/app{stripped}"
    qs = request.query_string.decode("utf-8")
    return f"{base}?{qs}" if qs else base


def _is_always_excluded(path: str) -> bool:
    """Return True if `path` falls under a permanently-excluded prefix, or
    contains a literal `..` path segment.

    The `..` check (found via Task 6.3 test migration — see the report for
    `_REDIRECT_EXCLUSION_PATTERNS`) exists because Werkzeug's test client
    (and some raw HTTP clients) do not normalize `..` segments the way a
    browser does before routing sees `request.path`; a path like
    `/investigations/../../etc/passwd/confirm` would otherwise match the
    `/investigations` prefix (its exclusion regexes require an *exact*
    `id/action` shape, which a `..`-laden path never has) and get
    302-redirected to an equally malformed `/app/...` URL. That was never
    exploitable (no filesystem access ever happens; a browser normalizes
    the Location header itself and lands on an ordinary same-origin 404),
    but it silently changed a handful of pre-existing "malformed id ->
    404" tests to "-> 302" as a side effect of retirement, which is worse
    behavior than necessary for zero benefit — so such paths are excluded
    from the registry entirely and fall through to Flask's normal
    dispatch/404, matching pre-Task-6.3 behavior exactly.
    """
    if any(segment == ".." for segment in path.split("/")):
        return True
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

    This is pure prefix-membership only — it does NOT know about the
    redirect exclusions/overrides above. Callers that need the actual
    dispatch decision (used by `init_react_dispatch`'s `before_request`
    hook) must additionally consult `_is_redirect_excluded`.
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

    Works regardless of *when* Jinja blueprints are registered relative to
    this call — the hook intercepts before Flask's URL-map dispatch ever
    runs. A matched, non-excluded path 302-redirects to its `/app/*`
    equivalent (D14); everything else falls through to normal Flask
    dispatch unchanged.
    """

    @app.before_request
    def _dispatch_react_owned_paths() -> ResponseReturnValue | None:
        path = request.path
        prefixes = get_react_owned_prefixes(current_app)
        if not matches_react_prefix(path, prefixes):
            return None
        if _is_redirect_excluded(path):
            return None
        return cast(
            "ResponseReturnValue",
            redirect(build_app_redirect_target(path), code=302),
        )
