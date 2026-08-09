"""Boot-time refusal tests for `BEEPER_AUTH_MODE` config (Task 8.3 — ADR
0002 §1/§8, FR54).

Exercises both the pure `validate_boot_config()` function AND the full
`create_app()` integration (so a refusal is proven to actually prevent app
construction, not just to be theoretically callable).
"""

from __future__ import annotations

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import AuthConfigError, Config, TestingConfig, validate_boot_config


class _LocalModeConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"


class _OidcModeConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"


class _OidcScimConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = True


class _NoneModeScimEnabledConfig(TestingConfig):
    BEEPER_AUTH_MODE = "none"
    BEEPER_SCIM_ENABLED = True


class _LocalModeScimEnabledConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"
    BEEPER_SCIM_ENABLED = True


class _BogusModeConfig(TestingConfig):
    BEEPER_AUTH_MODE = "bogus"


class TestValidateBootConfigDirectly:
    def test_mode_none_is_always_valid(self) -> None:
        validate_boot_config(Config)  # must not raise

    def test_unrecognized_mode_refused(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_AUTH_MODE"):
            validate_boot_config(_BogusModeConfig)

    def test_scim_enabled_outside_oidc_refused_for_none(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_SCIM_ENABLED"):
            validate_boot_config(_NoneModeScimEnabledConfig)

    def test_scim_enabled_outside_oidc_refused_for_local(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_SCIM_ENABLED"):
            validate_boot_config(_LocalModeScimEnabledConfig)

    def test_scim_enabled_inside_oidc_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        validate_boot_config(_OidcScimConfig)  # must not raise

    def test_local_mode_without_env_secret_key_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(AuthConfigError, match="SECRET_KEY"):
            validate_boot_config(_LocalModeConfig)

    def test_oidc_mode_without_env_secret_key_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(AuthConfigError, match="SECRET_KEY"):
            validate_boot_config(_OidcModeConfig)

    def test_local_mode_with_env_secret_key_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        validate_boot_config(_LocalModeConfig)  # must not raise

    def test_oidc_mode_with_env_secret_key_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        validate_boot_config(_OidcModeConfig)  # must not raise

    def test_mode_none_never_requires_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        validate_boot_config(TestingConfig)  # must not raise — mode defaults "none"

    def test_class_level_secret_key_alone_does_not_satisfy_the_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`TestingConfig.SECRET_KEY` is a hardcoded class attribute, NOT
        env-supplied — the check must look at `os.environ`, not
        `config.SECRET_KEY`, per the ADR's exact wording."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert TestingConfig.SECRET_KEY  # truthy class attribute...
        with pytest.raises(AuthConfigError, match="SECRET_KEY"):
            validate_boot_config(_LocalModeConfig)  # ...still refused


class TestCreateAppIntegration:
    def test_create_app_refuses_scim_outside_oidc(self) -> None:
        with pytest.raises(AuthConfigError):
            create_app(_LocalModeScimEnabledConfig)

    def test_create_app_refuses_local_mode_without_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(AuthConfigError):
            create_app(_LocalModeConfig)

    def test_create_app_boots_local_mode_with_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        app = create_app(_LocalModeConfig)
        assert app.config["BEEPER_AUTH_MODE"] == "local"

    def test_create_app_boots_oidc_scim_with_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        app = create_app(_OidcScimConfig)
        assert app.config["BEEPER_AUTH_MODE"] == "oidc"
        assert app.config["BEEPER_SCIM_ENABLED"] is True

    def test_create_app_still_boots_default_none_mode_with_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        app = create_app(TestingConfig)
        assert app.config["BEEPER_AUTH_MODE"] == "none"


class TestSessionCookieHardening:
    """ADR §2: HttpOnly on, SameSite=Lax, Secure driven explicitly by
    `BEEPER_EXTERNAL_SCHEME` (never inferred from request introspection) —
    applied ONLY in `local`/`oidc` mode. See `TestSessionCookieModeNoneUnaffected`
    below for the mode-`none` non-regression this class is paired with."""

    def test_default_scheme_is_https_and_secure_is_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        app = create_app(_LocalModeConfig)
        assert app.config["SESSION_COOKIE_SECURE"] is True

    def test_http_external_scheme_turns_secure_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")

        class _HttpConfig(_LocalModeConfig):
            BEEPER_EXTERNAL_SCHEME = "http"

        app = create_app(_HttpConfig)
        assert app.config["SESSION_COOKIE_SECURE"] is False

    def test_httponly_and_samesite_set_in_local_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        app = create_app(_LocalModeConfig)
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    def test_session_lifetime_default_is_eight_hours_in_oidc_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import timedelta

        monkeypatch.setenv("SECRET_KEY", "a-real-secret-key")
        app = create_app(_OidcModeConfig)
        assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=8)


class TestSessionCookieModeNoneUnaffected:
    """Self-review finding, fixed in `create_app()`: the session-cookie
    hardening block must be scoped to `local`/`oidc` ONLY. `beeper_ui.routes
    .knowledge`'s pre-existing `flash()` call (a live, un-migrated Jinja
    route reachable in mode `none`) is itself backed by Flask's session
    cookie — an unconditional `SESSION_COOKIE_SECURE=True` default would
    have broken that flash cookie over plain HTTP (the demo/
    `kubectl port-forward` access pattern), violating "mode `none`
    preserves today's behavior exactly" (NFR26). These assertions pin
    Flask's own untouched defaults in mode `none`."""

    def test_mode_none_leaves_secure_at_flask_default_false(self) -> None:
        app = create_app(TestingConfig)
        assert app.config["SESSION_COOKIE_SECURE"] is False

    def test_mode_none_leaves_samesite_at_flask_default_none(self) -> None:
        app = create_app(TestingConfig)
        assert app.config["SESSION_COOKIE_SAMESITE"] is None

    def test_mode_none_leaves_lifetime_at_flask_default_31_days(self) -> None:
        from datetime import timedelta

        app = create_app(TestingConfig)
        assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=31)

    def test_mode_none_httponly_still_true_via_flask_own_default(self) -> None:
        """HttpOnly is Flask's own default regardless — not evidence the
        8.3 hardening block ran, just confirming it stays true either way."""
        app = create_app(TestingConfig)
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True

    def test_mode_none_unaffected_even_with_https_external_scheme_set(self) -> None:
        """Belt-and-suspenders: even if `BEEPER_EXTERNAL_SCHEME` is
        (meaninglessly) set alongside mode `none`, the hardening block must
        still be skipped — the mode gate, not the scheme value, decides."""

        class _NoneModeWithSchemeConfig(TestingConfig):
            BEEPER_EXTERNAL_SCHEME = "https"

        app = create_app(_NoneModeWithSchemeConfig)
        assert app.config["SESSION_COOKIE_SECURE"] is False

    def test_real_flash_cookie_route_not_marked_secure_in_mode_none(self) -> None:
        """End-to-end proof, not just config-level: `POST
        /knowledge/<id>/confirm` (`beeper_ui.routes.knowledge.confirm_entry`)
        calls Flask's `flash()` on error, which sets a session cookie. In
        mode `none` (the demo default) that cookie must NOT carry the
        `Secure` attribute, or a browser accessing the demo over plain HTTP
        (`kubectl port-forward`) silently drops it and the flash message
        never appears — the exact regression this fix addresses."""
        from unittest.mock import MagicMock, patch

        from beeper_ui.services.kb_service import KBServiceError

        app = create_app(TestingConfig)
        with patch("beeper_ui.routes.knowledge.get_kb_service") as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.confirm_entry.side_effect = KBServiceError("boom")

            with app.test_client() as client:
                resp = client.post(
                    "/knowledge/kb-123/confirm", data={}, follow_redirects=False
                )
                assert resp.status_code == 302
                set_cookie_headers = resp.headers.get_all("Set-Cookie")
                assert set_cookie_headers, "flash() must have set a session cookie"
                assert not any("Secure" in h for h in set_cookie_headers), (
                    f"session cookie marked Secure in mode none: {set_cookie_headers}"
                )


class TestParseGroupNames:
    def test_parses_comma_separated(self) -> None:
        from beeper_ui.config import parse_group_names

        assert parse_group_names("Admins,beeper-admin") == ("Admins", "beeper-admin")

    def test_strips_whitespace_and_drops_empties(self) -> None:
        from beeper_ui.config import parse_group_names

        assert parse_group_names(" Admins , , beeper-admin ,") == ("Admins", "beeper-admin")

    def test_empty_string_yields_empty_tuple(self) -> None:
        from beeper_ui.config import parse_group_names

        assert parse_group_names("") == ()
