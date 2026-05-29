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
