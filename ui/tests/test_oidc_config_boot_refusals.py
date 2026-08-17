"""Boot-time refusal tests for `oidc`-mode-specific config (Task 8.5 — ADR
0002 §3/§8). Companion to `test_auth_config_boot_refusals.py` (Task 8.3's
`BEEPER_AUTH_MODE`/`BEEPER_SCIM_ENABLED`/`SECRET_KEY` refusals) — kept as
its own file per this suite's established per-task-file convention rather
than editing that one, since 8.6/8.8 run in parallel and shared-file
editing is additive-only append, not interleaving into another task's file.
"""

from __future__ import annotations

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import AuthConfigError, TestingConfig, validate_boot_config


class _OidcCompleteConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


class _OidcMissingIssuerConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = ""
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


class _OidcMissingClientIdConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = ""
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


class _OidcMissingClientSecretConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = ""


class _OidcMissingAllConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = ""
    BEEPER_OIDC_CLIENT_ID = ""
    BEEPER_OIDC_CLIENT_SECRET = ""


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-oidc-boot-tests")
    yield


class TestValidateBootConfigDirectly:
    def test_complete_oidc_config_is_valid(self) -> None:
        validate_boot_config(_OidcCompleteConfig)  # must not raise

    def test_missing_issuer_refused(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_OIDC_ISSUER"):
            validate_boot_config(_OidcMissingIssuerConfig)

    def test_missing_client_id_refused(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_OIDC_CLIENT_ID"):
            validate_boot_config(_OidcMissingClientIdConfig)

    def test_missing_client_secret_refused(self) -> None:
        with pytest.raises(AuthConfigError, match="BEEPER_OIDC_CLIENT_SECRET"):
            validate_boot_config(_OidcMissingClientSecretConfig)

    def test_missing_all_three_names_all_three(self) -> None:
        with pytest.raises(AuthConfigError) as exc_info:
            validate_boot_config(_OidcMissingAllConfig)
        message = str(exc_info.value)
        assert "BEEPER_OIDC_ISSUER" in message
        assert "BEEPER_OIDC_CLIENT_ID" in message
        assert "BEEPER_OIDC_CLIENT_SECRET" in message

    def test_local_mode_never_requires_oidc_config(self) -> None:
        class _LocalConfig(TestingConfig):
            BEEPER_AUTH_MODE = "local"

        validate_boot_config(_LocalConfig)  # must not raise

    def test_none_mode_never_requires_oidc_config(self) -> None:
        validate_boot_config(TestingConfig)  # must not raise — default mode


class TestCreateAppIntegration:
    def test_create_app_boots_with_complete_oidc_config(self) -> None:
        app = create_app(_OidcCompleteConfig)
        assert app.config["BEEPER_AUTH_MODE"] == "oidc"

    def test_create_app_refuses_oidc_missing_issuer(self) -> None:
        with pytest.raises(AuthConfigError):
            create_app(_OidcMissingIssuerConfig)

    def test_create_app_refuses_oidc_missing_client_id(self) -> None:
        with pytest.raises(AuthConfigError):
            create_app(_OidcMissingClientIdConfig)

    def test_create_app_refuses_oidc_missing_client_secret(self) -> None:
        with pytest.raises(AuthConfigError):
            create_app(_OidcMissingClientSecretConfig)

    def test_oidc_auth_blueprint_registered_only_in_oidc_mode(self) -> None:
        app = create_app(_OidcCompleteConfig)
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/auth/login" in rules
        assert "/auth/callback" in rules
        assert "/auth/logout" in rules

    def test_oidc_auth_blueprint_absent_in_local_mode(self) -> None:
        class _LocalConfig(TestingConfig):
            BEEPER_AUTH_MODE = "local"

        app = create_app(_LocalConfig)
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/auth/login" not in rules

    def test_oidc_auth_blueprint_absent_in_none_mode(self) -> None:
        app = create_app(TestingConfig)
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/auth/login" not in rules

    def test_auth_login_404s_when_not_registered(self) -> None:
        app = create_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get("/auth/login")
            assert resp.status_code == 404
