"""Local-mode admin bootstrap (Task 8.6 — ADR 0002 §6, FR61).

`ensure_bootstrap_admin(app)` runs once, at `create_app()` boot, in `local`
mode only (see `beeper_ui.app.create_app()`), and is deliberately
idempotent and non-destructive:

- Both `BEEPER_BOOTSTRAP_ADMIN_USERNAME` and `_PASSWORD` absent -> no-op,
  and NOT a boot refusal (unlike `beeper_ui.config.validate_boot_config()`'s
  `SECRET_KEY` check) — `flask create-admin` (`beeper_ui.cli`) is the
  documented alternate/recovery path (ADR §6), so a fresh `local`-mode
  deployment with no bootstrap Secret configured is a valid, if
  zero-admin, starting state. Mode `none` (the demo) never calls this
  function at all, so it requires zero bootstrap configuration by
  construction.
- Exactly one of the two env vars set -> refused with a logged ERROR
  (almost certainly a Helm/Secret authoring mistake — a username with no
  password, or vice versa) and no user created.
- The seeded username already exists in the store -> NEVER
  overwritten/recreated, regardless of whether `_PASSWORD` now differs
  from whatever created it (FR61: "a rotated password is never reverted
  by a restart" — an admin who rotated the account's password by hand
  keeps that password across every subsequent restart, even though the
  Secret/env still says the original one).
- Password shorter than `password_hashing.MIN_PASSWORD_LENGTH` -> refused
  with a logged ERROR, no user created (matches the same floor
  `flask create-admin` enforces).
- Otherwise -> `store.create_local_user(..., role="admin", active=True)`.

Deliberately reads `BEEPER_BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD` straight
from `os.environ` (never a `Config` class attribute) — the same freshness
reasoning `beeper_ui.config.validate_boot_config()`'s `SECRET_KEY` check
documents: a `Config` subclass attribute is frozen at class-definition
(import) time, so a test that `monkeypatch.setenv(...)` between two
`ensure_bootstrap_admin()` calls (e.g. the FR61 "restart with a rotated
password" AC) needs a live re-read, not a baked-in class attribute.

Regardless of which branch above ran, always finishes by calling
`IdentityStoreService.refresh_zero_admin_alarm()` — the boot-time
equivalent of the CRITICAL-log + `/health/api` flag every WRITE already
raises via `_after_mutation()` (ADR §5.3 / FR60 / FR61's "no seed + no
active admin ⇒ prominent startup ERROR (not a crash) + `/health/api`
flag").

The whole function body is wrapped in a broad `except Exception` — an
identity-store/Qdrant outage at boot must never crash `create_app()`
(FR61's "not a crash" guarantee is not scoped only to the missing-config
case; a transient infra hiccup during the bootstrap check should degrade
to a loud log line, not take the whole UI process down with it).
"""

from __future__ import annotations

import logging
import os

from flask import Flask

from beeper_ui.services.identity_store import get_identity_store
from beeper_ui.services.password_hashing import MIN_PASSWORD_LENGTH, hash_password

logger = logging.getLogger(__name__)

USERNAME_ENV = "BEEPER_BOOTSTRAP_ADMIN_USERNAME"
PASSWORD_ENV = "BEEPER_BOOTSTRAP_ADMIN_PASSWORD"


def ensure_bootstrap_admin(app: Flask) -> None:
    """Entry point — call once from `create_app()` when `BEEPER_AUTH_MODE ==
    "local"`. Never raises."""
    try:
        _ensure_bootstrap_admin(app)
    except Exception:
        logger.exception(
            "Bootstrap admin check failed unexpectedly (identity store "
            "unavailable?) — continuing boot regardless. See ADR 0002 "
            "§6 / FR61."
        )


def _ensure_bootstrap_admin(app: Flask) -> None:
    username = os.environ.get(USERNAME_ENV, "").strip()
    password = os.environ.get(PASSWORD_ENV, "")

    store = get_identity_store()

    if username or password:
        if not (username and password):
            logger.error(
                "%s and %s must both be set (or both left unset) for the "
                "bootstrap admin seed to run — exactly one was set. "
                "Bootstrap admin seed skipped. See ADR 0002 §6 / FR61.",
                USERNAME_ENV,
                PASSWORD_ENV,
            )
        elif store.get_by_username(username) is not None:
            logger.info(
                "Bootstrap admin username %r already exists in the "
                "identity store — left untouched (idempotent seed; FR61: "
                "a rotated password is never reverted by a restart).",
                username,
            )
        elif len(password) < MIN_PASSWORD_LENGTH:
            logger.error(
                "%s is shorter than the %d-character minimum — bootstrap "
                "admin seed skipped. See ADR 0002 §6.",
                PASSWORD_ENV,
                MIN_PASSWORD_LENGTH,
            )
        else:
            store.create_local_user(
                user_name=username,
                password_hash=hash_password(password),
                display_name=username,
                role="admin",
                active=True,
            )
            logger.warning(
                "Bootstrap admin %r created from %s/%s.",
                username,
                USERNAME_ENV,
                PASSWORD_ENV,
            )

    if store.refresh_zero_admin_alarm():
        logger.error(
            "local-mode boot completed with ZERO active admins in the "
            "identity store — no caller can complete any admin-gated "
            "action until one exists. Recovery: `flask --app beeper_ui "
            "create-admin <username>` (see ADR 0002 §6 / FR61), or set "
            "%s/%s and restart. This is reported at /health/api too "
            "(`zero_active_admins`).",
            USERNAME_ENV,
            PASSWORD_ENV,
        )
