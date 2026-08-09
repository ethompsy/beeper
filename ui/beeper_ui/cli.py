"""Flask CLI commands (Task 8.6 — ADR 0002 §6, FR61's recovery path).

`flask --app beeper_ui create-admin <username>` — the documented recovery
path when `local`-mode boots with zero active admins (no bootstrap Secret
configured, or the last admin was demoted/deactivated by mistake): "the
recovery/secondary path is `flask --app beeper_ui create-admin <username>`
(`--password-stdin`; documented `kubectl exec` runbook)" (ADR §6).

Registered unconditionally by `register_cli()` (not gated on
`BEEPER_AUTH_MODE`) — the command is harmless to have present in `none`/
`oidc` mode (it still writes through `IdentityStoreService`'s public
`create_local_user`/`update_user`, which work regardless of which mode is
currently *serving* logins) and gating CLI *registration* on runtime config
would only complicate the one thing this command needs to guarantee: that
it works from a `kubectl exec` shell into a pod that may be
mid-troubleshooting a broken `BEEPER_AUTH_MODE` value in the first place.
"""

from __future__ import annotations

import getpass
import sys

import click
from flask import Flask

from beeper_ui.services.identity_store import DuplicateUserError, get_identity_store
from beeper_ui.services.password_hashing import MIN_PASSWORD_LENGTH, hash_password


def register_cli(app: Flask) -> None:
    """Register `flask create-admin` on `app`."""
    app.cli.add_command(create_admin_command)


@click.command("create-admin")
@click.argument("username")
@click.option(
    "--password",
    default=None,
    help="Password. Omit to be prompted interactively, or use --password-stdin.",
)
@click.option(
    "--password-stdin",
    is_flag=True,
    default=False,
    help=(
        "Read the password from stdin — the non-interactive `kubectl exec` "
        "recovery path, e.g.: "
        "`echo \"$PASS\" | kubectl exec -i <pod> -- flask --app beeper_ui "
        "create-admin alice --password-stdin`."
    ),
)
@click.option(
    "--display-name",
    default=None,
    help="Display name (defaults to the username).",
)
def create_admin_command(
    username: str,
    password: str | None,
    password_stdin: bool,
    display_name: str | None,
) -> None:
    """Create a local admin user, or promote/reactivate an existing one.

    USERNAME is the login username (case-insensitive; matches the store's
    `user_name_lc` uniqueness key).

    Non-interactive via `--password` or `--password-stdin`; otherwise
    prompts twice (no echo, via `getpass`) and confirms the two match.

    If USERNAME already exists, this command does NOT create a duplicate
    or touch its password — it only promotes the existing record to an
    active admin (`role="admin"`, `active=True`). This covers the most
    likely zero-active-admins recovery scenario alongside "nobody was
    ever seeded": an existing user was demoted or deactivated by mistake.
    """
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")

    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            click.echo("Passwords do not match.", err=True)
            raise SystemExit(1)

    if len(password) < MIN_PASSWORD_LENGTH:
        click.echo(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", err=True
        )
        raise SystemExit(1)

    store = get_identity_store()
    existing = store.get_by_username(username)
    if existing is not None:
        store.update_user(existing.id, role="admin", active=True)
        click.echo(f"Existing user {username!r} promoted to active admin.")
        return

    try:
        store.create_local_user(
            user_name=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            role="admin",
            active=True,
        )
    except DuplicateUserError:
        click.echo(
            f"User {username!r} already exists (race with a concurrent create).",
            err=True,
        )
        raise SystemExit(1) from None

    click.echo(f"Admin user {username!r} created.")
