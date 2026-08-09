"""Light doc-guard for Task 8.9's deployment-guide.md additions.

Mirrors `test_route_parity_targets.py`'s pattern (pure-parse, no Flask app,
no frontend build) — narrower in scope since `docs/deployment-guide.md` had
no existing parse-guard to extend (Task 8.9's own acceptance criterion: "the
deployment guide contains the required sections... extend the existing
docs-parse test pattern if one covers deployment-guide, else add a light
one").

This does not re-validate every fact in the guide (that's the human
reviewer's job); it pins the presence of the specific sections/callouts the
Task 8.9 acceptance criteria name explicitly, so a future edit that
accidentally deletes one of them (e.g. during an unrelated docs pass) fails
loudly instead of silently regressing operator-facing documentation.
"""

from __future__ import annotations

from pathlib import Path

_UI_DIR = Path(__file__).parent.parent
_REPO_ROOT = _UI_DIR.parent
_GUIDE_PATH = _REPO_ROOT / "docs" / "deployment-guide.md"
_ADR_0001_PATH = (
    _REPO_ROOT
    / "docs"
    / "specs"
    / "decisions"
    / "0001-rbac-and-realtime-collaboration-in-react-ui.md"
)


def _guide_text() -> str:
    return _GUIDE_PATH.read_text()


class TestAuthenticationIdentityConfigReference:
    """(a) the three auth modes + the `ui.auth` values reference."""

    def test_section_heading_present(self):
        assert "### Authentication & Identity" in _guide_text()

    def test_all_three_modes_documented(self):
        text = _guide_text()
        for mode in ("`none`", "`local`", "`oidc`"):
            assert mode in text

    def test_ui_auth_values_keys_documented(self):
        text = _guide_text()
        for key in (
            "ui.auth.mode",
            "ui.auth.existingSecret",
            "ui.auth.externalScheme",
            "ui.auth.sessionLifetimeHours",
            "ui.auth.adminGroups",
            "ui.auth.scim.enabled",
            "ui.auth.bootstrap.enabled",
        ):
            assert key in text, f"{key} missing from the ui.auth values reference"


class TestScimTokenAdminEquivalentAndRotation:
    """(b) SCIM token = admin-equivalent secret + the dual-token rotation
    runbook."""

    def test_admin_equivalent_statement_present(self):
        text = _guide_text()
        assert "admin-equivalent secret" in text

    def test_rotation_runbook_covers_all_steps(self):
        text = _guide_text()
        for marker in (
            "scimTokenSecondary",
            "rollout restart",
            "Repoint your IdP",
            "Promote:",
        ):
            assert marker in text, f"rotation runbook missing step: {marker!r}"


class TestBootstrapAndLockoutRecovery:
    """(c) bootstrap + lockout recovery (`kubectl exec ... flask
    create-admin`; zero-admin CRITICAL alarm + `/health/api` flag)."""

    def test_create_admin_cli_command_documented(self):
        text = _guide_text()
        assert "flask --app beeper_ui" in text
        assert "create-admin" in text
        assert "kubectl exec" in text

    def test_zero_admin_health_flag_documented(self):
        assert "zero_active_admins" in _guide_text()


class TestIdpSetupNotes:
    """(d) IdP setup notes for Okta/Entra/Keycloak incl. the Entra
    externalId->objectId mapping and the RP-initiated-logout-without-
    id_token_hint caveat."""

    def test_all_three_idps_covered(self):
        text = _guide_text()
        for idp in ("Okta", "Entra", "Keycloak"):
            assert idp in text

    def test_entra_external_id_object_id_mapping_documented(self):
        text = _guide_text()
        assert "externalId" in text
        assert "objectId" in text
        assert "not `sub`" in text or "not the OIDC" in text

    def test_rp_initiated_logout_caveat_documented(self):
        text = _guide_text()
        assert "id_token_hint" in text


class TestScimNetworkPolicyHonesty:
    """The NetworkPolicy row (plan-doc deliverable 4): must not overclaim
    path-level SCIM isolation."""

    def test_l3_l4_honesty_note_present(self):
        text = _guide_text()
        assert "L3/L4" in text
        assert "cannot" in text.lower()


class TestAdr0001ClosingNote:
    """(e) ADR 0001 §8 gains a closing note pointing at ADR 0002, and the
    "production has no admin path" caveat is marked superseded rather than
    silently deleted (history preserved, corrected inline)."""

    def test_closing_note_present(self):
        text = _ADR_0001_PATH.read_text()
        assert "Closing note" in text
        assert "0002-oidc-scim-and-local-fallback-identity.md" in text

    def test_superseded_caveat_still_readable_but_marked_corrected(self):
        text = _ADR_0001_PATH.read_text()
        # The original historical sentence stays (it was true at the time)
        # but the closing note must explicitly say it's no longer current.
        assert "production has no path to the `admin` role at all" in text
        assert "no longer true" in text
