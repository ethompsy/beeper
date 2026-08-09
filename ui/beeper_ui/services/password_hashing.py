"""Argon2id password hashing (Task 8.6 — ADR 0002 §6, FR59).

`ui/pyproject.toml` gains exactly one new dependency for this: `argon2-cffi`
(the maintained, CFFI-backed binding to the reference Argon2 C library —
never a hand-rolled KDF, per ADR 0001 §4's "auth is easy to get subtly
wrong" doctrine that also governs Task 8.5's choice of Authlib).

── Parameters chosen (cite: RFC 9106 §4 "Parameter Choice") ────────────────

RFC 9106 §4 names exactly two recommended Argon2id parameter sets:

  1. "If much memory is available ... and the guessing difficulty is not
     limited by other factors ... 2 GiB of memory, t=1, p=4."
  2. "If much less memory is available, a possible parameter selection is
     ... 64 MiB of memory, t=3, p=4" ("the SECOND RECOMMENDED option").

This module uses RFC 9106's **second** ("less memory") profile —
`memory_cost=65536` KiB (64 MiB), `time_cost=3`, `parallelism=4` — because
it matches this deployment's actual shape: a single-replica Flask pod (ADR
0002 §11's named invariant: "revisit before `ui.replicaCount > 1`") with no
dedicated memory budget, not a highmem host provisioned specifically to
absorb the first profile's 2 GiB-per-concurrent-hash cost. `hash_len=32`
and `salt_len=16` are RFC 9106's own recommended output/salt lengths
(§3.1). These five values are also `argon2-cffi`'s own `PasswordHasher`
library defaults (unchanged since v21) — pinned here as explicit constants
rather than left implicit, so a future `argon2-cffi` major version
bumping its defaults can never silently change what Beeper actually
verifies against.

`MIN_PASSWORD_LENGTH = 12`: ADR 0002 §6 — "min length 12, no
composition/rotation policy — NIST 800-63-aligned" (NIST SP 800-63B §5.1.1.2
recommends a length floor over composition rules).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# RFC 9106 §4, "second recommended option" (low-memory environments).
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KIB = 65536  # 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

MIN_PASSWORD_LENGTH = 12

_HASHER = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST_KIB,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
)

# A fixed hash of an arbitrary, never-issued password — used by the login
# route (`beeper_ui.routes.auth`) to run a full Argon2id verify against
# an UNKNOWN username, so an unknown-user login takes the same CPU time as
# a real (wrong-password) verify. Computed once at import time, not
# per-request. See `beeper_ui.routes.auth`'s module docstring for the full
# uniform-401 / constant-delay design this feeds into.
DUMMY_PASSWORD_HASH: str = _HASHER.hash("beeper-dummy-hash-for-timing-normalization-only")


def hash_password(password: str) -> str:
    """Hash `password` with Argon2id, the parameters pinned above.

    Returns the full encoded hash string (`argon2-cffi` embeds the
    algorithm variant + all parameters + salt in the output, e.g.
    `$argon2id$v=19$m=65536,t=3,p=4$...`), suitable for storing verbatim
    in `UserRecord.password_hash` and passing straight back into
    `verify_password()` later — no separate salt/param storage needed.
    """
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-shape verify: `True` on match, `False` on ANY failure mode
    (wrong password, malformed/foreign hash string) — never raises.

    Deliberately requires a real `password_hash` string (no `None`
    shortcut here): callers that might not have a real hash for the
    principal being checked (e.g. an unknown username, or a user with no
    local password at all) MUST substitute `DUMMY_PASSWORD_HASH` before
    calling this, so the Argon2id computation always actually runs and
    costs the same CPU time either way — skipping the call entirely for a
    "no such user"/"no password set" case is exactly the timing side
    channel FR59's uniform-401 requirement exists to close.
    """
    try:
        return _HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if `password_hash` was produced with different parameters than
    the ones pinned above (e.g. a future parameter bump) — callers with
    write access (the login route, on successful auth) may use this to
    opportunistically re-hash and persist the upgraded hash. Not wired up
    automatically by this module; see `beeper_ui.routes.auth` for whether
    a given call site opts in.
    """
    return _HASHER.check_needs_rehash(password_hash)
