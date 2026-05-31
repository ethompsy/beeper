"""Static validation of the demo deployment & port-forward automation (Task 6.1).

Per AD-8 the demo lifecycle is verified manually against a live cluster, but the
*config correctness* that makes those runs reproducible IS statically checkable.
These tests parse the Makefile / kind-config / helm values and assert the
contracts that the Task 6.1 fixes establish, so the specific bugs that broke
repeatability (leaked port-forwards, a no-op `wait`, a missing operator-API
forward, a kind/NodePort mismatch) cannot silently regress.

Pure Python + pyyaml — no kubectl/kind/docker required.
"""

import os
import re

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAKEFILE = os.path.join(REPO_ROOT, "Makefile")
KIND_CONFIG = os.path.join(REPO_ROOT, "kind-config.yaml")
VALUES_DEV = os.path.join(REPO_ROOT, "helm", "beeper", "values-dev.yaml")
UI_SVC_TEMPLATE = os.path.join(
    REPO_ROOT, "helm", "beeper", "templates", "ui-deployment.yaml"
)
DEMO_README = os.path.join(REPO_ROOT, "demo", "README.md")


def _read(path):
    with open(path) as f:
        return f.read()


def _recipe(name):
    """Return the lines of a Makefile recipe (the indented block after `name:`)."""
    text = _read(MAKEFILE)
    lines = text.splitlines()
    out, capturing = [], False
    for line in lines:
        if re.match(rf"^{re.escape(name)}:", line):
            capturing = True
            continue
        if capturing:
            # Recipe lines are tab-indented; a non-indented non-blank line ends it.
            if line and not line.startswith(("\t", " ")) and not line.startswith("#"):
                break
            out.append(line)
    return "\n".join(out)


def _recipe_code(name):
    """Recipe with comment lines stripped, for asserting on actual shell code
    (so prose in `@#`/`#` comments can't trip content checks)."""
    return "\n".join(
        ln
        for ln in _recipe(name).splitlines()
        if not re.match(r"^\s*@?#", ln)
    )


class TestQdrantPortForwardNoLeak:
    """AC: `make demo-deploy` initialises Qdrant without leaking a port-forward.

    Regression guard for the `... &` on one recipe line + `kill %1` on another
    (separate shells → the forward was never killed → :6333 stayed bound and the
    next demo-deploy/demo-up failed).
    """

    def test_demo_deploy_has_no_bare_kill_percent_job(self):
        recipe = _recipe_code("demo-deploy")
        assert "kill %1" not in recipe, (
            "`kill %1` cannot work across Make's per-line shells; use a single "
            "shell with a trapped PID"
        )

    def test_demo_deploy_qdrant_forward_is_single_shell_with_trap(self):
        recipe = _recipe("demo-deploy")
        assert "port-forward svc/beeper-qdrant" in recipe
        # The forward, the init/seed, and the kill must live in ONE shell:
        # captured PID + EXIT trap is the contract.
        assert "PF_PID=$$!" in recipe
        assert "trap " in recipe and "EXIT" in recipe
        assert "kill $$PF_PID" in recipe

    def test_demo_deploy_still_runs_init_and_seed(self):
        recipe = _recipe("demo-deploy")
        assert "init-collections.py" in recipe
        assert "seed_kb.py" in recipe


class TestDemoUiPortForwards:
    """AC: `make demo-ui` forwards Beeper UI, operator API, and OTel frontend,
    and the recipe blocks (so Ctrl+C can tear the forwards down)."""

    def test_demo_ui_forwards_beeper_ui(self):
        assert "port-forward svc/beeper-ui 5050:80" in _recipe("demo-ui")

    def test_demo_ui_forwards_operator_api(self):
        # Finding C: without this the UI's backend calls 503 ("operator down").
        recipe = _recipe("demo-ui")
        assert "port-forward svc/beeper-operator" in recipe
        assert "8081:8080" in recipe

    def test_demo_ui_forwards_otel_frontend_and_jaeger(self):
        recipe = _recipe("demo-ui")
        assert "port-forward svc/frontend-proxy 8080:8080" in recipe
        assert "port-forward svc/jaeger 16686:16686" in recipe

    def test_demo_ui_waits_and_traps_in_one_shell(self):
        """The forwards (`&`), the `trap`, and `wait` must be one line-continued
        block — otherwise `wait` runs in its own shell with no children and
        returns instantly, orphaning the forwards (old bug)."""
        recipe = _recipe("demo-ui")
        # Find the contiguous backslash-continued block that contains `wait`.
        block_lines, buf = [], []
        for line in recipe.splitlines():
            buf.append(line)
            if not line.rstrip().endswith("\\"):
                if any("wait" == ln.strip() or ln.strip().endswith("wait") for ln in buf):
                    block_lines = buf
                    break
                buf = []
        block = "\n".join(block_lines)
        assert "wait" in block, "demo-ui must end on a blocking `wait`"
        assert "trap " in block and "kill 0" in block, (
            "the wait/forwards block must trap INT/TERM/EXIT to clean up forwards"
        )
        assert block.count("port-forward") >= 4, (
            "all four port-forwards must share the single waited shell"
        )


def _kind_ui_host_to_node():
    doc = yaml.safe_load(_read(KIND_CONFIG))
    mappings = doc["nodes"][0]["extraPortMappings"]
    by_host = {m["hostPort"]: m["containerPort"] for m in mappings}
    return by_host


class TestKindNodePortConsistency:
    """AC: kind-config port mappings are correct for the Beeper UI — the kind
    host->node mapping must match the pinned Service nodePort (Finding D)."""

    def test_kind_maps_5050_to_30050(self):
        assert _kind_ui_host_to_node().get(5050) == 30050

    def test_ui_service_nodeport_is_pinned_to_30050(self):
        values = yaml.safe_load(_read(VALUES_DEV))
        assert values["ui"]["service"]["type"] == "NodePort"
        assert values["ui"]["service"]["nodePort"] == 30050, (
            "UI nodePort must be pinned so kind's 5050->30050 mapping reaches it"
        )

    def test_kind_and_values_nodeport_agree(self):
        kind_node_port = _kind_ui_host_to_node().get(5050)
        values = yaml.safe_load(_read(VALUES_DEV))
        assert kind_node_port == values["ui"]["service"]["nodePort"]

    def test_ui_template_supports_nodeport(self):
        assert "nodePort:" in _read(UI_SVC_TEMPLATE), (
            "chart Service template must render a nodePort for pinning to work"
        )

    def test_kind_config_valid_two_node_cluster(self):
        doc = yaml.safe_load(_read(KIND_CONFIG))
        assert doc["kind"] == "Cluster"
        roles = [n["role"] for n in doc["nodes"]]
        assert "control-plane" in roles and "worker" in roles


class TestQdrantVersion:
    """AC: Helm-deployed Qdrant runs v1.15.0 (D2 — align chart with local dev to
    avoid KB read/write discrepancies)."""

    def test_values_dev_pins_qdrant_v1_15_0(self):
        values = yaml.safe_load(_read(VALUES_DEV))
        assert values["qdrant"]["image"]["tag"] == "v1.15.0"


# --- Task 6.2: fault injection & recovery --------------------------------------

# Valid flagd variants per fault flag, from the opentelemetry-demo chart's
# demo.flagd.json (captured live 2026-05-29). Encodes the contract demo-fault
# relies on so an invalid variant (e.g. imageSlowLoad has no "on") is caught
# statically instead of only failing at flagd-resolve time during a live demo.
FLAGD_VARIANTS = {
    "paymentFailure": {"100%", "90%", "75%", "50%", "25%", "10%", "off"},
    "cartFailure": {"on", "off"},
    "kafkaQueueProblems": {"on", "off"},
    "imageSlowLoad": {"10sec", "5sec", "off"},
    "adHighCpu": {"on", "off"},
}


def _parse_demo_fault_cases():
    """Parse demo-fault's case arms: {fault-name: (FLAG_KEY, ON_VARIANT)}.

    Returns the LITERAL variant as flagd receives it. IMPORTANT: `%` is NOT
    special in Make *recipes* (only in pattern rules / functions), so `%%` is
    passed through verbatim — it does NOT collapse to `%`. Writing `100%%` set
    flagd's defaultVariant to the non-existent `100%%` variant and silently
    broke the payment-failure fault (the primary demo fault). This parser
    therefore does NOT collapse `%%`, so that bug is caught, not hidden.
    """
    recipe = _recipe("demo-fault")
    cases = {}
    for m in re.finditer(
        r"^\s*([a-z][a-z-]+]?\))\s*FLAG_KEY=(\w+);\s*ON_VARIANT=('?[^ ;']+'?)",
        recipe,
        re.MULTILINE,
    ):
        name = m.group(1).rstrip(")")
        flag = m.group(2)
        variant = m.group(3).strip("'")
        cases[name] = (flag, variant)
    return cases


class TestFaultInjectionMapping:
    """AC: `make demo-fault FAULT=<name>` injects a real fault (FR37); the named
    faults each map to a valid, non-off flagd variant."""

    def test_criterion_faults_are_handled(self):
        cases = _parse_demo_fault_cases()
        for name in ("payment-failure", "cart-failure", "high-cpu"):
            assert name in cases, f"demo-fault must handle FAULT={name}"

    def test_every_fault_uses_a_valid_nonoff_variant(self):
        """Regression guard for slow-images -> imageSlowLoad=on (no such variant;
        imageSlowLoad is 10sec/5sec/off)."""
        cases = _parse_demo_fault_cases()
        for name, (flag, variant) in cases.items():
            assert flag in FLAGD_VARIANTS, f"{name}: unknown flag {flag}"
            assert variant in FLAGD_VARIANTS[flag], (
                f"{name}: ON_VARIANT={variant!r} is not a valid variant of "
                f"{flag} ({sorted(FLAGD_VARIANTS[flag])})"
            )
            assert variant != "off", f"{name}: enabling a fault must not set 'off'"

    def test_payment_failure_uses_100_percent(self):
        flag, variant = _parse_demo_fault_cases()["payment-failure"]
        assert flag == "paymentFailure" and variant == "100%"

    def test_fault_list_matches_case_handler(self):
        """Advertised faults (demo-fault-list) == handled faults (demo-fault).

        Names are printed as `@echo "  <name>   <description>"`, so match a
        2-space-indented token inside the echo strings (the description column
        is separated by 2+ spaces; usage lines like `make demo-recover` use a
        single space and are excluded)."""
        listed = set(re.findall(r'"  ([a-z][a-z-]+) {2,}', _recipe("demo-fault-list")))
        handled = set(_parse_demo_fault_cases())
        assert handled == listed, (
            f"handled-only: {handled - listed}; advertised-only: {listed - handled}"
        )

    def test_demo_fault_requires_FAULT_arg(self):
        assert 'test -n "$(FAULT)"' in _recipe("demo-fault")

    def test_demo_fault_rejects_unknown_fault(self):
        recipe = _recipe("demo-fault")
        assert "Unknown fault" in recipe and "exit 1" in recipe


class TestFaultRecovery:
    """AC: `make demo-recover` clears all faults (FR38)."""

    def test_recover_disables_all_flags(self):
        recipe = _recipe_code("demo-recover")
        assert "state']='DISABLED'" in recipe or "'state']='DISABLED'" in recipe
        assert "defaultVariant']='off'" in recipe

    def test_recover_iterates_every_flag(self):
        # Must reset ALL flags, not a single one, so any active fault is cleared.
        recipe = _recipe_code("demo-recover")
        assert "for f in flags" in recipe or "flags.get('flags'" in recipe

    def test_recover_restarts_flagd(self):
        assert "rollout restart deploy/flagd" in _recipe("demo-recover")


class TestLlmKeyGate:
    """AC (demo robustness, Finding H): demo-beeper must not hard-fail when no
    LLM API key is set if the deploy uses a local provider (ollama)."""

    def test_demo_beeper_allows_missing_key_for_ollama(self):
        recipe = _recipe("demo-beeper")
        # Detects the provider and treats ollama/local as not requiring a key.
        assert "values-dev.yaml" in recipe and "provider:" in recipe
        assert 'LLM_PROVIDER" = "ollama"' in recipe or "ollama" in recipe
        # Still creates the secret (placeholder) so the chart's secretKeyRef resolves.
        assert "placeholder" in recipe.lower()
        assert "kubectl create secret generic llm-credentials" in recipe

    def test_demo_beeper_still_errors_for_cloud_without_key(self):
        recipe = _recipe("demo-beeper")
        assert "exit 1" in recipe  # cloud provider + no key still fails fast


class TestDemoReadmeScript:
    """AC (6.3): demo/README.md documents the full demo script with timing
    (2–3 min warmup; 5–10 min investigation) and the 3/3 repeatability run."""

    def test_readme_has_full_demo_script_section(self):
        readme = _read(DEMO_README)
        assert re.search(r"Full Demo Script|3/3 Validation", readme), (
            "README must document the end-to-end demo script"
        )

    def test_readme_documents_warmup_and_investigation_timing(self):
        readme = _read(DEMO_README).lower()
        assert "warmup" in readme
        # 2–3 min warmup and 5–10 min investigation timings present
        assert re.search(r"2[–-]3\s*min", readme), "missing ~2–3 min warmup timing"
        assert re.search(r"5[–-]10\s*min", readme), "missing ~5–10 min investigation timing"

    def test_readme_documents_three_consecutive_runs(self):
        readme = _read(DEMO_README).lower()
        assert "3" in readme and (
            "consecutive" in readme or "3/3" in readme or "3×" in readme or "3x" in readme
        )

    def test_readme_covers_recover_and_no_insufficient_data(self):
        readme = _read(DEMO_README).lower()
        assert "demo-recover" in readme
        assert "insufficient data" in readme  # the zero-insufficient-data [T]

    def test_readme_fault_flag_names_match_makefile(self):
        """The README fault table must use the SAME flag keys as demo-fault
        (guards the doc drift where it said paymentServiceFailure etc.)."""
        readme = _read(DEMO_README)
        case_flags = {flag for (flag, _v) in _parse_demo_fault_cases().values()}
        for flag in case_flags:
            assert flag in readme, f"README must document the real flag key {flag!r}"
        # And must NOT reference the old wrong names.
        for wrong in ("paymentServiceFailure", "cartServiceFailure", "adServiceHighCpu"):
            assert wrong not in readme, f"stale/incorrect flag name in README: {wrong}"
