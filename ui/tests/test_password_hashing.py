"""Tests for `beeper_ui.services.password_hashing` (Task 8.6 — FR59).

AC [T]: "argon2id hash/verify round-trip; hash parameters asserted."
"""

from __future__ import annotations

from beeper_ui.services.password_hashing import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST_KIB,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LEN,
    ARGON2_TIME_COST,
    DUMMY_PASSWORD_HASH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)


class TestParameters:
    """RFC 9106 §4 "second recommended option" (low-memory): m=65536 KiB
    (64 MiB), t=3, p=4 — pinned as explicit constants, not left to library
    defaults."""

    def test_pinned_argon2id_parameters(self) -> None:
        assert ARGON2_TIME_COST == 3
        assert ARGON2_MEMORY_COST_KIB == 65536
        assert ARGON2_PARALLELISM == 4
        assert ARGON2_HASH_LEN == 32
        assert ARGON2_SALT_LEN == 16

    def test_min_password_length_is_twelve(self) -> None:
        # ADR 0002 §6: "min length 12 ... NIST 800-63-aligned".
        assert MIN_PASSWORD_LENGTH == 12


class TestHashPassword:
    def test_hash_is_argon2id_and_carries_the_pinned_parameters(self) -> None:
        digest = hash_password("correct horse battery staple")
        assert digest.startswith("$argon2id$")
        assert f"m={ARGON2_MEMORY_COST_KIB}" in digest
        assert f"t={ARGON2_TIME_COST}" in digest
        assert f"p={ARGON2_PARALLELISM}" in digest

    def test_two_hashes_of_the_same_password_differ(self) -> None:
        # Random salt per hash (ARGON2_SALT_LEN bytes) — proves salting is
        # actually happening, not a deterministic/unsalted digest.
        a = hash_password("same-password-both-times")
        b = hash_password("same-password-both-times")
        assert a != b


class TestVerifyPassword:
    def test_round_trip_correct_password_verifies(self) -> None:
        digest = hash_password("my-strong-passphrase-1")
        assert verify_password(digest, "my-strong-passphrase-1") is True

    def test_wrong_password_does_not_verify(self) -> None:
        digest = hash_password("my-strong-passphrase-1")
        assert verify_password(digest, "totally-different") is False

    def test_malformed_hash_string_returns_false_not_raise(self) -> None:
        assert verify_password("not-a-real-hash", "anything") is False

    def test_empty_hash_string_returns_false_not_raise(self) -> None:
        assert verify_password("", "anything") is False

    def test_dummy_hash_never_verifies_against_any_real_password_attempt(self) -> None:
        # The timing-normalization dummy hash must never accidentally
        # accept a real user's password.
        assert verify_password(DUMMY_PASSWORD_HASH, "password") is False
        assert verify_password(DUMMY_PASSWORD_HASH, "") is False

    def test_dummy_hash_is_a_valid_argon2id_hash_with_pinned_parameters(self) -> None:
        # It must actually cost real Argon2id CPU time to verify against —
        # a malformed placeholder would short-circuit and defeat the whole
        # point of using it for timing normalization (see routes/auth.py).
        assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")
        assert f"m={ARGON2_MEMORY_COST_KIB}" in DUMMY_PASSWORD_HASH


class TestNeedsRehash:
    def test_freshly_hashed_password_does_not_need_rehash(self) -> None:
        digest = hash_password("current-parameters")
        assert needs_rehash(digest) is False

    def test_hash_with_different_parameters_needs_rehash(self) -> None:
        # A hash produced with weaker-than-pinned parameters should be
        # flagged for opportunistic upgrade.
        from argon2 import PasswordHasher

        weaker = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
        digest = weaker.hash("legacy-password")
        assert needs_rehash(digest) is True
