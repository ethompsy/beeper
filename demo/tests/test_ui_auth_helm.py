"""Static validation of the `ui.auth` Helm tree (Task 8.9, ADR 0002 §8).

Two tiers, deliberately separated:

1. **Pure Python + pyyaml/regex — no kubectl/kind/docker/helm required**,
   matching this package's existing convention
   (`test_demo_automation.py`'s module docstring). These are the tests that
   run in CI's `demo-config` job (`pytest demo/tests -q`, which installs
   only `pytest`+`pyyaml`) and are the primary enforcement for NFR26 demo
   invariance: they parse `values.yaml`/`values-dev.yaml`/
   `ui-deployment.yaml` as text/YAML and assert the *structural* guarantee
   that makes byte-identical mode-`none` output true — the whole identity
   env block sits behind one `{{- if ne .Values.ui.auth.mode "none" }}`
   guard, and neither `values.yaml`'s default nor `values-dev.yaml`
   (untouched by this task) sets `ui.auth.mode` away from "none".

2. A small **helm-binary-guarded** tier (`TestUiAuthHelmTemplateRenders`,
   skipped via `shutil.which("helm")` when the binary isn't installed —
   this repo's own `make demo-*` targets already depend on Helm, so it is
   present in most dev/orchestrator environments even though CI's
   `demo-config` job doesn't install it) that renders the chart for
   real and checks the actual output, as an extra golden-render safety
   net beyond the text-level guarantee above.

The full `helm template` byte-diff against pre-Task-8.9 `main` (both
default and `values-dev.yaml`) was additionally performed once, by hand,
and is reported in the Task 8.9 delivery notes — not re-run as a permanent
test, since it requires a second git ref to diff against and pytest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VALUES_MAIN = os.path.join(REPO_ROOT, "helm", "beeper", "values.yaml")
VALUES_DEV = os.path.join(REPO_ROOT, "helm", "beeper", "values-dev.yaml")
UI_DEPLOYMENT_TEMPLATE = os.path.join(
    REPO_ROOT, "helm", "beeper", "templates", "ui-deployment.yaml"
)
UI_NETWORKPOLICY_TEMPLATE = os.path.join(
    REPO_ROOT, "helm", "beeper", "templates", "ui-networkpolicy.yaml"
)
CONFIG_PY = os.path.join(REPO_ROOT, "ui", "beeper_ui", "config.py")
BOOTSTRAP_PY = os.path.join(REPO_ROOT, "ui", "beeper_ui", "services", "bootstrap.py")
CHART_DIR = os.path.join(REPO_ROOT, "helm", "beeper")
EXAMPLES_DIR = os.path.join(CHART_DIR, "examples")

# The complete set of identity-related env vars ADR 0002 §8 / Task 8.9 wires
# from the `ui.auth` values tree, mapped to the values-tree path that drives
# each one (informational — the actual per-mode assertions live below).
# `SECRET_KEY` is the one entry with no `BEEPER_` prefix (it's Flask's own
# session-signing config, not an app-specific setting).
IDENTITY_ENV_VARS = frozenset(
    {
        "SECRET_KEY",
        "BEEPER_AUTH_MODE",
        "BEEPER_EXTERNAL_SCHEME",
        "BEEPER_SESSION_LIFETIME_HOURS",
        "BEEPER_ADMIN_GROUPS",
        "BEEPER_USER_GROUPS",
        "BEEPER_OIDC_ISSUER",
        "BEEPER_OIDC_CLIENT_ID",
        "BEEPER_OIDC_CLIENT_SECRET",
        "BEEPER_OIDC_REDIRECT_URL",
        "BEEPER_OIDC_SCOPES",
        "BEEPER_OIDC_GROUPS_CLAIM",
        "BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL",
        "BEEPER_SCIM_ENABLED",
        "BEEPER_SCIM_STRICT",
        "BEEPER_SCIM_TOKEN",
        "BEEPER_SCIM_TOKEN_SECONDARY",
        "BEEPER_BOOTSTRAP_ADMIN_USERNAME",
        "BEEPER_BOOTSTRAP_ADMIN_PASSWORD",
    }
)

# The 5 pre-Task-8.9 env vars — pinned verbatim so a future edit that
# accidentally moves one of them *inside* the identity-mode guard (breaking
# mode-`none` output) fails loudly here rather than only in a manual helm
# diff.
PRE_EXISTING_ENV_VARS = (
    "FLASK_ENV",
    "BEEPER_UI_PORT",
    "BEEPER_OPERATOR_URL",
    "QDRANT_HOST",
    "QDRANT_PORT",
)

# The Secret keys the `existingSecret` pattern defines (ADR §8 / values.yaml
# comment block) and the env var each backs.
SECRET_KEY_TO_ENV = {
    "secretKey": "SECRET_KEY",
    "clientSecret": "BEEPER_OIDC_CLIENT_SECRET",
    "scimToken": "BEEPER_SCIM_TOKEN",
    "scimTokenSecondary": "BEEPER_SCIM_TOKEN_SECONDARY",
    "bootstrapUsername": "BEEPER_BOOTSTRAP_ADMIN_USERNAME",
    "bootstrapPassword": "BEEPER_BOOTSTRAP_ADMIN_PASSWORD",
}

MODE_GUARD = '{{- if ne .Values.ui.auth.mode "none" }}'


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _config_py_env_names() -> set[str]:
    """Every `BEEPER_*` env var name `os.environ.get("...")` reads in
    config.py, plus the two bootstrap.py module constants (which are read
    straight from `os.environ`, deliberately never a frozen Config class
    attribute — see bootstrap.py's module docstring) and `SECRET_KEY`
    itself (config.py's `Config.SECRET_KEY = os.environ.get("SECRET_KEY", ...)`
    — the one non-`BEEPER_`-prefixed entry)."""
    # `\s*` (unlike `.`) matches newlines without needing re.DOTALL, so this
    # also catches the multi-line calls, e.g.:
    #   BEEPER_OIDC_SCOPES: str = os.environ.get(
    #       "BEEPER_OIDC_SCOPES", "openid profile email groups"
    #   )
    # and the boolean flags, which go through `_env_bool(...)` instead of
    # `os.environ.get(...)` directly (see config.py's `_env_bool` helper).
    names = set(
        re.findall(
            r'(?:os\.environ\.get|_env_bool)\(\s*"(BEEPER_[A-Z_]+)"', _read(CONFIG_PY)
        )
    )
    names.add("SECRET_KEY")
    bootstrap_src = _read(BOOTSTRAP_PY)
    for const in ("USERNAME_ENV", "PASSWORD_ENV"):
        match = re.search(rf'{const}\s*=\s*"(BEEPER_[A-Z_]+)"', bootstrap_src)
        assert match, f"{const} not found in bootstrap.py — env-name test is stale"
        names.add(match.group(1))
    return names


def _deployment_template_env_names() -> set[str]:
    """Every `- name: XXX` env var name anywhere in ui-deployment.yaml."""
    return set(re.findall(r"- name:\s*(\S+)", _read(UI_DEPLOYMENT_TEMPLATE)))


class TestUiAuthEnvWiringMatchesConfig:
    """AC: "env wiring matches config.py names exactly (static test greps
    both sides)"."""

    def test_every_identity_env_var_is_actually_read_by_the_app(self):
        """Catches a typo'd env name in the Helm template that would
        silently no-op (Kubernetes doesn't validate env var names against
        anything the app reads)."""
        app_names = _config_py_env_names()
        missing = IDENTITY_ENV_VARS - app_names
        assert not missing, (
            f"Helm wires {sorted(missing)} but ui/beeper_ui/config.py (or "
            "bootstrap.py) does not read them under those exact names — "
            "grep both sides before trusting this env var does anything."
        )

    def test_every_identity_env_var_is_wired_in_the_deployment_template(self):
        """The inverse check: every identity env var config.py/bootstrap.py
        knows about is actually wired somewhere in the Deployment template
        — catches an env var ADR 0002 added to config.py that Task 8.9
        forgot to wire into Helm."""
        template_names = _deployment_template_env_names()
        missing = IDENTITY_ENV_VARS - template_names
        assert not missing, (
            f"{sorted(missing)} are read by the app but never appear as "
            "`- name: <VAR>` anywhere in ui-deployment.yaml."
        )

    def test_no_stray_beeper_env_var_wired_that_config_py_does_not_read(self):
        """The full symmetric check restricted to the identity set (the
        template also wires pre-existing non-identity vars like
        BEEPER_UI_PORT/BEEPER_OPERATOR_URL, which are intentionally out of
        this set)."""
        template_identity_names = _deployment_template_env_names() & (
            IDENTITY_ENV_VARS
            | {n for n in _deployment_template_env_names() if n.startswith("BEEPER_")}
        )
        # Every BEEPER_-prefixed (or SECRET_KEY) name the template wires
        # must be something config.py/bootstrap.py actually reads.
        app_names = _config_py_env_names()
        stray = {
            n
            for n in template_identity_names
            if (n.startswith("BEEPER_") or n == "SECRET_KEY") and n not in app_names
        }
        assert not stray, (
            f"ui-deployment.yaml wires {sorted(stray)}, which "
            "ui/beeper_ui/config.py never reads — dead Helm config."
        )


class TestUiAuthDemoInvariance:
    """AC: NFR26 — with default values (`mode: none`) the rendered UI
    manifest is byte-identical to pre-Task-8.9 output. Enforced here at the
    *template-text* level (no helm binary required — see
    TestUiAuthHelmTemplateRenders below for the rendered-output-level
    proof, and this task's delivery notes for the one-time `helm template`
    diff against `main`)."""

    def test_chart_default_auth_mode_is_none(self):
        values = yaml.safe_load(_read(VALUES_MAIN))
        assert values["ui"]["auth"]["mode"] == "none"

    def test_chart_default_existing_secret_is_empty(self):
        values = yaml.safe_load(_read(VALUES_MAIN))
        assert values["ui"]["auth"]["existingSecret"] == ""

    def test_demo_values_do_not_override_ui_auth_at_all(self):
        """`values-dev.yaml` is untouched by Task 8.9 — the strongest
        possible form of "demo values unchanged": there is nothing to
        regress because there is nothing there. Confirmed by the merged
        result inheriting the chart default (`mode: none`) rather than by
        any dev-values override."""
        dev_values = yaml.safe_load(_read(VALUES_DEV))
        assert "auth" not in dev_values.get("ui", {}), (
            "values-dev.yaml must not set ui.auth.* — the demo's identity "
            "posture is 'inherit the chart default (none)', not 'this "
            "file explicitly requests none'; an override here (even a "
            "matching one) would defeat this invariance test's purpose."
        )

    def test_identity_env_block_is_entirely_behind_the_mode_none_guard(self):
        """The structural guarantee that makes mode-none output
        byte-identical: everything after the pre-existing 5 env vars is
        gated by exactly one `{{- if ne .Values.ui.auth.mode "none" }}`,
        and none of the identity env var names appear anywhere BEFORE that
        guard in the template source."""
        template = _read(UI_DEPLOYMENT_TEMPLATE)
        assert template.count(MODE_GUARD) == 1, (
            "expected exactly one mode-none guard gating the whole "
            "identity env block — a second one suggests the block was "
            "split, which risks a var leaking outside the gate"
        )
        before, _, after = template.partition(MODE_GUARD)
        for var in IDENTITY_ENV_VARS:
            assert f"- name: {var}" not in before, (
                f"{var} appears before the mode-none guard — it would "
                "render even when ui.auth.mode is the default 'none', "
                "breaking NFR26 demo invariance"
            )
            assert f"- name: {var}" in after, (
                f"{var} never appears after the mode-none guard at all"
            )

    def test_pre_existing_env_vars_are_unconditional(self):
        """The original 5 env vars must NOT have been pulled inside any
        new conditional — they render in every mode, exactly as before."""
        template = _read(UI_DEPLOYMENT_TEMPLATE)
        before_guard = template.partition(MODE_GUARD)[0]
        for var in PRE_EXISTING_ENV_VARS:
            assert f"- name: {var}" in before_guard, (
                f"{var} is expected unconditionally, before any ui.auth "
                "gating — a regression here changes mode-none output"
            )


class TestUiAuthSecretPattern:
    """AC: "existingSecret pattern: no plaintext secrets in values;
    Secret-absent + mode=none templates fine"."""

    def test_values_yaml_never_assigns_a_secret_key_a_literal_value(self):
        """Structural check: the only way a Secret-key name
        (secretKey/clientSecret/scimToken/scimTokenSecondary/
        bootstrapUsername/bootstrapPassword) may appear as a YAML mapping
        key anywhere under `ui.auth` in values.yaml or values-dev.yaml is
        nowhere at all — they are Secret keys, never values-tree keys.
        (They legitimately appear in prose comments describing the
        existingSecret contract; this check parses the loaded YAML
        structure, not the raw text, so comments can't trip it.)"""
        for path in (VALUES_MAIN, VALUES_DEV):
            values = yaml.safe_load(_read(path))
            auth = values.get("ui", {}).get("auth", {})
            leaked = _find_keys(auth, set(SECRET_KEY_TO_ENV))
            assert not leaked, f"{path} defines {leaked} directly under ui.auth"

    def test_every_secret_backed_env_var_is_optional(self):
        """Every `secretKeyRef` in the Deployment template sets
        `optional: true` (design choice: a Secret missing a key must never
        crash-loop the pod at the Kubernetes layer — the app's own
        boot-time `validate_boot_config()` or SCIM request-time check
        produces a clearer error instead)."""
        template = _read(UI_DEPLOYMENT_TEMPLATE)
        blocks = re.findall(
            r"secretKeyRef:\n(?:\s+\S.*\n){1,4}", template
        )
        assert len(blocks) == len(SECRET_KEY_TO_ENV), (
            f"expected {len(SECRET_KEY_TO_ENV)} secretKeyRef blocks (one "
            f"per {sorted(SECRET_KEY_TO_ENV)}), found {len(blocks)}"
        )
        for block in blocks:
            assert "optional: true" in block, f"missing optional: true in:\n{block}"

    def test_every_secret_key_name_referenced_matches_the_documented_contract(self):
        template = _read(UI_DEPLOYMENT_TEMPLATE)
        referenced_keys = set(re.findall(r"key:\s*(\w+)\n\s*optional:", template))
        assert referenced_keys == set(SECRET_KEY_TO_ENV), (
            f"Secret keys referenced in the template {sorted(referenced_keys)} "
            f"must exactly match the documented contract {sorted(SECRET_KEY_TO_ENV)}"
        )

    def test_example_secret_manifest_has_no_real_secret_committed(self):
        """The example Secret manifest must only ever contain obvious
        placeholders, never something that looks like a real generated
        token (this is a committed example file, not `--from-literal`
        usage)."""
        example = _read(os.path.join(EXAMPLES_DIR, "identity-secret.yaml"))
        for key in SECRET_KEY_TO_ENV:
            match = re.search(rf"^\s*{key}:\s*(\S.*)$", example, re.MULTILINE)
            assert match, f"{key} missing from the example Secret manifest"
            value = match.group(1).strip()
            # Placeholders are angle-bracketed or the documented literal
            # demo values (admin / a plain example username) — never a
            # bare 32+ char hex/base64-looking string, which would read as
            # a real committed secret.
            assert value.startswith("<") or value in {"admin"}, (
                f"{key}: {value!r} in the example manifest looks like a "
                "real value, not a placeholder"
            )


def _find_keys(node: object, wanted: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in wanted:
                found.add(k)
            found |= _find_keys(v, wanted)
    elif isinstance(node, list):
        for item in node:
            found |= _find_keys(item, wanted)
    return found


class TestUiAuthNetworkPolicy:
    """AC: "Optional SCIM NetworkPolicy" row — disabled by default,
    L3/L4-honest, and refuses to render a silent allow-all."""

    def test_disabled_by_default(self):
        values = yaml.safe_load(_read(VALUES_MAIN))
        np = values["ui"]["auth"]["scim"]["networkPolicy"]
        assert np["enabled"] is False
        assert np["allowFrom"] == []

    def test_template_gated_on_enabled(self):
        template = _read(UI_NETWORKPOLICY_TEMPLATE)
        assert "{{- if .Values.ui.auth.scim.networkPolicy.enabled }}" in template

    def test_template_fails_fast_on_empty_allow_from(self):
        """Guards the documented Kubernetes footgun: an empty NetworkPolicy
        ingress `from` list means allow-ALL, not deny-all."""
        template = _read(UI_NETWORKPOLICY_TEMPLATE)
        assert "{{- fail " in template
        assert "allowFrom" in template.split("{{- fail ")[1].split("}}")[0] or (
            "allowFrom" in template
        )

    def test_honesty_note_present_and_not_scoped_to_a_path(self):
        """The template must not claim it restricts `/scim/v2` specifically
        — NetworkPolicy can't do that, and the docs/values comments say so.
        This test is a tripwire against a future "helpful" rename that
        reintroduces the overclaim."""
        template = _read(UI_NETWORKPOLICY_TEMPLATE)
        assert "L3/L4" in template
        assert "podSelector" in template
        # The policy selects the whole ui component, not a per-path rule.
        assert "app.kubernetes.io/component: ui" in template


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm binary not installed")
class TestUiAuthHelmTemplateRenders:
    """Extra golden-render safety net beyond the text-level tests above —
    skipped when `helm` isn't on PATH (not assumed by CI's `demo-config`
    job, which installs only pytest+pyyaml; present in most dev/
    orchestrator environments since `make demo-*` already requires it)."""

    def _template(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["helm", "template", "beeper", CHART_DIR, *args],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    @staticmethod
    def _ui_deployment_env_names(rendered_yaml: str) -> list[str]:
        """Parse full multi-doc `helm template` output and return the UI
        Deployment container's env var names, in order.

        Deliberately full YAML parsing, not regex-over-text: `helm
        template` groups output by Kind (Services before Deployments)
        rather than preserving source-file order, so a naive "first
        `component: ui` label, then the next `env:`" regex can walk into
        an unrelated resource's block (verified: it silently matched the
        Operator Deployment's env when the UI Service, which has no `env`
        key at all, sorted immediately ahead of it).
        """
        for doc in yaml.safe_load_all(rendered_yaml):
            if not doc:
                continue
            if doc.get("kind") == "Deployment" and doc.get("metadata", {}).get(
                "name", ""
            ).endswith("-ui"):
                containers = doc["spec"]["template"]["spec"]["containers"]
                assert len(containers) == 1
                return [e["name"] for e in containers[0].get("env", [])]
        raise AssertionError("no Deployment named *-ui found in rendered output")

    def test_default_values_render_the_original_five_env_vars_only(self):
        result = self._template()
        assert result.returncode == 0, result.stderr
        names = self._ui_deployment_env_names(result.stdout)
        assert names == list(PRE_EXISTING_ENV_VARS), names

    def test_values_dev_renders_the_original_five_env_vars_only(self):
        result = self._template("-f", VALUES_DEV)
        assert result.returncode == 0, result.stderr
        names = self._ui_deployment_env_names(result.stdout)
        assert names == list(PRE_EXISTING_ENV_VARS), names

    @pytest.mark.parametrize(
        "example_file",
        [
            "values-identity-local.yaml",
            "values-identity-oidc.yaml",
            "values-identity-oidc-scim.yaml",
        ],
    )
    def test_example_values_render_cleanly(self, example_file):
        result = self._template("-f", os.path.join(EXAMPLES_DIR, example_file))
        assert result.returncode == 0, result.stderr
        assert "BEEPER_AUTH_MODE" in result.stdout

    @pytest.mark.parametrize(
        "example_file",
        [
            None,
            "values-dev.yaml",
            "examples/values-identity-local.yaml",
            "examples/values-identity-oidc.yaml",
            "examples/values-identity-oidc-scim.yaml",
        ],
    )
    def test_helm_lint_clean(self, example_file):
        args = ["helm", "lint", CHART_DIR]
        if example_file:
            args += ["-f", os.path.join(CHART_DIR, example_file)]
        result = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_networkpolicy_absent_by_default(self):
        result = self._template()
        assert "kind: NetworkPolicy" not in result.stdout

    def test_networkpolicy_enabled_without_allow_from_fails(self):
        result = self._template("--set", "ui.auth.scim.networkPolicy.enabled=true")
        assert result.returncode != 0
        assert "allowFrom" in result.stderr

    def test_networkpolicy_enabled_with_allow_from_renders(self):
        result = self._template(
            "--set",
            "ui.auth.scim.networkPolicy.enabled=true",
            "--set",
            "ui.auth.scim.networkPolicy.allowFrom[0].ipBlock.cidr=203.0.113.0/24",
        )
        assert result.returncode == 0, result.stderr
        assert "kind: NetworkPolicy" in result.stdout
