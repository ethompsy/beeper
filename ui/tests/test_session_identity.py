"""Unit tests for `beeper_ui.middleware.session` (Task 8.3 — ADR 0002 §2's
"session core"), tested directly against a bare Flask app/request context
per the module's own stated design goal.

Includes targeted coverage for the security-review fixes: CSRF scheme
comparison (MEDIUM), malformed `exp`/`iat` coercion (LOW), and
case-insensitive host comparison (LOW).
"""

from __future__ import annotations

import time

import pytest
from flask import Flask, session

from beeper_ui.middleware.session import (
    build_login_redirect_next,
    clear_session_identity,
    establish_session_identity,
    read_session_identity,
    same_origin_request,
)


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["BEEPER_EXTERNAL_SCHEME"] = "http"
    return app


class TestEstablishAndReadRoundtrip:
    def test_roundtrip(self, app: Flask) -> None:
        with app.test_request_context("/"):
            established = establish_session_identity(
                sub="user-1", email="Alice@Corp.com", name="Alice", role_snapshot="admin"
            )
            read_back = read_session_identity()
            assert read_back is not None
            assert read_back.sub == "user-1"
            assert read_back.email == "Alice@Corp.com"
            assert read_back.email_lc == "alice@corp.com"
            assert read_back.role_snapshot == "admin"
            assert read_back == established

    def test_establish_rotates_prior_session_content(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["unrelated_pre_login_key"] = "attacker-fixed-value"
            establish_session_identity(sub="user-2")
            assert "unrelated_pre_login_key" not in session

    def test_read_with_no_identity_returns_none(self, app: Flask) -> None:
        with app.test_request_context("/"):
            assert read_session_identity() is None

    def test_clear_removes_identity(self, app: Flask) -> None:
        with app.test_request_context("/"):
            establish_session_identity(sub="user-3")
            clear_session_identity()
            assert read_session_identity() is None

    def test_expired_identity_returns_none_and_clears(self, app: Flask) -> None:
        with app.test_request_context("/"):
            establish_session_identity(sub="user-4", lifetime_hours=-1)  # already expired
            assert read_session_identity() is None
            assert "identity" not in session

    def test_default_lifetime_is_eight_hours(self, app: Flask) -> None:
        with app.test_request_context("/"):
            identity = establish_session_identity(sub="user-5")
            assert identity.exp - identity.iat == pytest.approx(8 * 3600)

    def test_no_email_leaves_email_lc_none(self, app: Flask) -> None:
        with app.test_request_context("/"):
            establish_session_identity(sub="user-6")
            identity = read_session_identity()
            assert identity is not None
            assert identity.email is None
            assert identity.email_lc is None


class TestMalformedSessionPayload:
    """Security review LOW finding, fixed: a malformed `exp`/`iat` must be
    treated as an invalid session, never raise out of `read_session_identity()`."""

    def test_missing_sub_key_returns_none(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {"exp": time.time() + 3600}  # no "sub"
            assert read_session_identity() is None

    def test_non_numeric_exp_returns_none_not_raise(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {"sub": "user-1", "exp": "not-a-number"}
            assert read_session_identity() is None

    def test_non_numeric_iat_returns_none_not_raise(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {
                "sub": "user-1",
                "iat": "not-a-number",
                "exp": time.time() + 3600,
            }
            assert read_session_identity() is None

    def test_none_exp_returns_none_not_raise(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {"sub": "user-1", "exp": None}
            assert read_session_identity() is None

    def test_missing_exp_defaults_to_already_expired(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {"sub": "user-1"}  # no exp at all
            assert read_session_identity() is None

    def test_malformed_payload_is_cleared_from_session(self, app: Flask) -> None:
        with app.test_request_context("/"):
            session["identity"] = {"sub": "user-1", "exp": "garbage"}
            read_session_identity()
            assert "identity" not in session


class TestBuildLoginRedirectNext:
    def test_uses_request_full_path_by_default(self, app: Flask) -> None:
        with app.test_request_context("/investigations/inv-1?status=open"):
            assert build_login_redirect_next() == "/investigations/inv-1?status=open"

    def test_no_query_string_has_no_dangling_question_mark(self, app: Flask) -> None:
        with app.test_request_context("/investigations"):
            assert build_login_redirect_next() == "/investigations"

    def test_explicit_path_argument_overrides_request(self, app: Flask) -> None:
        with app.test_request_context("/"):
            assert build_login_redirect_next("/custom/path") == "/custom/path"


class TestSameOriginRequest:
    """Security review MEDIUM fix: scheme is now part of the comparison,
    not just host. `app` fixture sets `BEEPER_EXTERNAL_SCHEME=http`."""

    def test_matching_scheme_and_host_allowed(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "http://localhost"}
        ):
            assert same_origin_request() is True

    def test_matching_host_wrong_scheme_rejected(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "https://localhost"}
        ):
            assert same_origin_request() is False

    def test_wrong_host_rejected(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "http://evil.example.com"}
        ):
            assert same_origin_request() is False

    def test_referer_fallback_used_when_origin_absent(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Referer": "http://localhost/page"}
        ):
            assert same_origin_request() is True

    def test_origin_preferred_over_referer_when_both_present(self, app: Flask) -> None:
        with app.test_request_context(
            "/x",
            method="POST",
            headers={
                "Origin": "http://evil.example.com",
                "Referer": "http://localhost/page",
            },
        ):
            assert same_origin_request() is False

    def test_missing_both_headers_rejected(self, app: Flask) -> None:
        with app.test_request_context("/x", method="POST"):
            assert same_origin_request() is False

    def test_malformed_origin_rejected(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "not a url \x00"}
        ):
            assert same_origin_request() is False

    def test_host_comparison_is_case_insensitive(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "http://LOCALHOST"}
        ):
            assert same_origin_request() is True

    def test_scheme_comparison_is_case_insensitive(self, app: Flask) -> None:
        with app.test_request_context(
            "/x", method="POST", headers={"Origin": "HTTP://localhost"}
        ):
            assert same_origin_request() is True

    def test_default_expected_scheme_is_https_when_unconfigured(self) -> None:
        """Without an explicit `BEEPER_EXTERNAL_SCHEME`, the safer default
        (https) is expected — an unconfigured deployment fails closed
        toward requiring TLS-matching origins, not open."""
        bare_app = Flask(__name__)
        bare_app.config["SECRET_KEY"] = "test-secret"
        with bare_app.test_request_context(
            "/x", method="POST", headers={"Origin": "http://localhost"}
        ):
            assert same_origin_request() is False  # http != default-expected https

        with bare_app.test_request_context(
            "/x", method="POST", headers={"Origin": "https://localhost"}
        ):
            assert same_origin_request() is True
