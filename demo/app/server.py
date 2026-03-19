"""
Beeper Demo Application Server.

A multi-role Flask HTTP server that serves as all four demo microservices
(api-gateway, backend, database, worker) based on the SERVICE_ROLE env var.

Each role exposes Prometheus metrics, structured JSON logging, health endpoints,
and configurable fault injection with runtime control via REST API.
"""

import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_ROLE = os.environ.get("SERVICE_ROLE", "backend")
SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8080"))
FAULT_ENABLED = os.environ.get("FAULT_ENABLED", "false").lower() == "true"
FAULT_TYPE = os.environ.get("FAULT_TYPE", "none")
SYNTHETIC_TRAFFIC = os.environ.get("SYNTHETIC_TRAFFIC", "false").lower() == "true"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8081")
DATABASE_URL = os.environ.get("DATABASE_URL", "http://localhost:8082")

# ---------------------------------------------------------------------------
# Structured JSON Logging
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname.lower(),
            "service": SERVICE_ROLE,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging():
    """Configure structured JSON logging to stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    "demo_request_total",
    "Total requests",
    ["service", "method", "endpoint", "status"],
    registry=registry,
)

REQUEST_DURATION = Histogram(
    "demo_request_duration_seconds",
    "Request duration in seconds",
    ["service", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=registry,
)

ERROR_COUNT = Counter(
    "demo_error_total",
    "Total errors",
    ["service", "error_type"],
    registry=registry,
)

ACTIVE_CONNECTIONS = Gauge(
    "demo_active_connections",
    "Active connections",
    ["service"],
    registry=registry,
)

# Fault injection metrics (Task 3)
FAULT_INJECTION_ACTIVE = Gauge(
    "demo_fault_injection_active",
    "Whether a fault injection is currently active (1=active, 0=inactive)",
    ["service", "fault_type"],
    registry=registry,
)

FAULT_INJECTION_TOTAL = Counter(
    "demo_fault_injection_total",
    "Total number of fault injections triggered",
    ["service", "fault_type"],
    registry=registry,
)

MEMORY_LEAK_BYTES = Gauge(
    "demo_memory_leak_bytes",
    "Bytes accumulated by memory leak fault injection",
    ["service"],
    registry=registry,
)

# Lifecycle demonstration metrics (Story 8-3, Task 3)
LIFECYCLE_STAGE = Gauge(
    "demo_lifecycle_stage",
    "Current lifecycle demonstration stage (1=active, 0=inactive)",
    ["service", "stage"],
    registry=registry,
)

LIFECYCLE_DURATION = Gauge(
    "demo_lifecycle_duration_seconds",
    "Total elapsed time for current lifecycle demonstration run",
    ["service"],
    registry=registry,
)

LIFECYCLE_RUNS_TOTAL = Counter(
    "demo_lifecycle_runs_total",
    "Total number of lifecycle demonstrations completed",
    ["service"],
    registry=registry,
)

# ---------------------------------------------------------------------------
# Fault Type Catalog (Task 2)
# ---------------------------------------------------------------------------

FAULT_TYPES = {
    "memory-leak": {
        "description": "Gradual memory leak — accumulates configurable chunks per request, "
                       "simulating a memory leak leading to eventual OOM.",
        "default_params": {"chunk_size_kb": 100},
        "expected_beeper_response": "Detect memory anomaly via container metrics, "
                                   "investigate OOM risk, propose resource limit adjustment or restart.",
    },
    "bad-deploy": {
        "description": "Bad deployment simulation — returns HTTP 500 errors at a high rate, "
                       "simulating a broken code deploy.",
        "default_params": {"error_rate": 0.8},
        "expected_beeper_response": "Detect error rate spike via SLO burn rate alert, "
                                   "investigate recent deployment, propose rollback.",
    },
    "cascading-failure": {
        "description": "Cascading failure — errors propagate from the injected service "
                       "to its upstream dependents, simulating real-world failure cascades.",
        "default_params": {"error_rate": 0.9},
        "expected_beeper_response": "Detect correlated failures across services, "
                                   "trace dependency chain to identify root cause service.",
    },
    "scale-dependent": {
        "description": "Scale-dependent latency — response time increases proportionally "
                       "with concurrent request count, simulating resource contention under load.",
        "default_params": {"base_latency_ms": 50, "per_connection_ms": 200},
        "expected_beeper_response": "Detect latency anomaly via SLO burn rate, "
                                   "investigate scaling metrics, propose HPA or resource adjustment.",
    },
}

# ---------------------------------------------------------------------------
# Runtime Fault State (Task 1)
# ---------------------------------------------------------------------------


def _create_fault_state():
    """Create a fresh fault state dict."""
    return {
        "fault_active": False,
        "fault_type": "none",
        "params": {},
        "started_at": None,
        "memory_leak_store": [],
        "memory_leak_bytes": 0,
    }


# Default state initialized from env vars
_default_fault_state = _create_fault_state()
if FAULT_ENABLED and FAULT_TYPE != "none":
    _default_fault_state["fault_active"] = True
    _default_fault_state["fault_type"] = FAULT_TYPE
    _default_fault_state["started_at"] = datetime.now(timezone.utc).isoformat()
    if FAULT_TYPE in FAULT_TYPES:
        _default_fault_state["params"] = dict(FAULT_TYPES[FAULT_TYPE]["default_params"])


def _get_fault_state(app):
    """Get the fault state from the app config, falling back to default."""
    if "fault_state" not in app.config:
        app.config["fault_state"] = dict(_default_fault_state)
        app.config["fault_state"]["memory_leak_store"] = list(
            _default_fault_state["memory_leak_store"]
        )
    return app.config["fault_state"]


# ---------------------------------------------------------------------------
# Lifecycle Demonstration Orchestrator (Story 8-3)
# ---------------------------------------------------------------------------

LIFECYCLE_STAGES = [
    "healthy",
    "fault_injected",
    "detecting",
    "investigating",
    "fix_proposed",
    "fix_applied",
    "verifying",
    "recovered",
    "kb_created",
]

DEFAULT_LIFECYCLE_TIMING = {
    "detect_seconds": 8,
    "investigate_seconds": 15,
    "fix_propose_seconds": 5,
    "fix_apply_seconds": 5,
    "verify_seconds": 10,
    "recover_seconds": 5,
    "kb_create_seconds": 5,
}

# Mapping from stage to the timing key that controls how long to wait before
# advancing TO the next stage (i.e., how long this stage lasts).
_STAGE_TIMING_KEY = {
    "fault_injected": "detect_seconds",
    "detecting": "investigate_seconds",
    "investigating": "fix_propose_seconds",
    "fix_proposed": "fix_apply_seconds",
    "fix_applied": "verify_seconds",
    "verifying": "recover_seconds",
    "recovered": "kb_create_seconds",
}

LIFECYCLE_NARRATION = {
    "healthy": (
        "The application is running normally. All services are healthy "
        "and meeting their SLO targets."
    ),
    "fault_injected": (
        "A {fault_type} has been introduced. In a real production environment, "
        "this could happen due to a bad deployment, resource exhaustion, "
        "or infrastructure failure."
    ),
    "detecting": (
        "Beeper's monitoring has detected an anomaly. The SLO burn rate "
        "has spiked, triggering an automatic investigation."
    ),
    "investigating": (
        "Beeper is now autonomously investigating the root cause. It's analyzing "
        "metrics, logs, and service dependencies to identify what went wrong."
    ),
    "fix_proposed": (
        "Beeper has identified the root cause and is proposing a fix. "
        "At trust level {trust_level}, it can apply this fix automatically."
    ),
    "fix_applied": (
        "The fix has been applied. Beeper is now verifying that the issue "
        "is truly resolved by monitoring the affected metrics."
    ),
    "verifying": (
        "Verification in progress. Beeper is confirming that SLO metrics "
        "have returned to normal and no new issues have emerged."
    ),
    "recovered": (
        "The service has fully recovered. All SLOs are back within target. "
        "The incident took {elapsed} to resolve — fully autonomously."
    ),
    "kb_created": (
        "Beeper has created a knowledge base entry documenting this incident. "
        "Next time a similar issue occurs, resolution will be even faster."
    ),
}


def _create_lifecycle_state():
    """Create a fresh lifecycle state dict."""
    return {
        "lifecycle_active": False,
        "current_stage": "healthy",
        "fault_type": "none",
        "trust_level": 5,
        "timing": dict(DEFAULT_LIFECYCLE_TIMING),
        "started_at": None,
        "stage_history": [],
        "timers": [],
    }


def _get_lifecycle_state(app):
    """Get the lifecycle state from the app config, falling back to default."""
    if "lifecycle_state" not in app.config:
        app.config["lifecycle_state"] = _create_lifecycle_state()
    return app.config["lifecycle_state"]


def _format_elapsed(ms):
    """Format milliseconds as a human-readable duration string."""
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes = int(seconds // 60)
    remaining = seconds % 60
    return f"{minutes}m {remaining:.0f}s"


def _get_narrative(stage, fault_type, trust_level, elapsed_ms):
    """Get the investor-friendly narrative for a lifecycle stage."""
    template = LIFECYCLE_NARRATION.get(stage, "")
    return template.format(
        fault_type=fault_type,
        trust_level=trust_level,
        elapsed=_format_elapsed(elapsed_ms),
    )


def _advance_lifecycle(app, active_role):
    """Advance the lifecycle to the next stage."""
    state = _get_lifecycle_state(app)
    if not state["lifecycle_active"]:
        return

    current = state["current_stage"]
    try:
        idx = LIFECYCLE_STAGES.index(current)
    except ValueError:
        return

    if idx >= len(LIFECYCLE_STAGES) - 1:
        # Already at final stage — no further advancement needed
        state["lifecycle_active"] = False
        return

    now = datetime.now(timezone.utc)
    elapsed_ms = (now - datetime.fromisoformat(state["started_at"])).total_seconds() * 1000

    # Close current stage duration
    if state["stage_history"]:
        last = state["stage_history"][-1]
        if last["duration_ms"] is None:
            last["duration_ms"] = int(
                (now - datetime.fromisoformat(last["timestamp"])).total_seconds() * 1000
            )

    # Advance to next stage
    next_stage = LIFECYCLE_STAGES[idx + 1]

    # Clear previous stage metric, set new one
    LIFECYCLE_STAGE.labels(service=active_role, stage=current).set(0)
    LIFECYCLE_STAGE.labels(service=active_role, stage=next_stage).set(1)
    LIFECYCLE_DURATION.labels(service=active_role).set(elapsed_ms / 1000.0)

    narrative = _get_narrative(next_stage, state["fault_type"], state["trust_level"], elapsed_ms)

    state["current_stage"] = next_stage
    state["stage_history"].append({
        "stage": next_stage,
        "timestamp": now.isoformat(),
        "duration_ms": None,
        "narrative": narrative,
    })

    # If this is the "recovered" stage, clear faults
    if next_stage == "recovered":
        fault_state = _get_fault_state(app)
        if fault_state["fault_active"]:
            prev_type = fault_state["fault_type"]
            fault_state["fault_active"] = False
            fault_state["fault_type"] = "none"
            fault_state["params"] = {}
            fault_state["started_at"] = None
            fault_state["memory_leak_store"].clear()
            fault_state["memory_leak_bytes"] = 0
            MEMORY_LEAK_BYTES.labels(service=active_role).set(0)
            if prev_type in FAULT_TYPES:
                FAULT_INJECTION_ACTIVE.labels(
                    service=active_role, fault_type=prev_type
                ).set(0)

    # If this is the final stage (kb_created), mark lifecycle complete
    if next_stage == "kb_created":
        now_final = datetime.now(timezone.utc)
        final_elapsed = (
            now_final - datetime.fromisoformat(state["started_at"])
        ).total_seconds() * 1000
        state["stage_history"][-1]["duration_ms"] = 0
        state["lifecycle_active"] = False
        LIFECYCLE_DURATION.labels(service=active_role).set(final_elapsed / 1000.0)
        LIFECYCLE_RUNS_TOTAL.labels(service=active_role).inc()
        return

    # Schedule next advancement (only in non-TESTING mode)
    timing_key = _STAGE_TIMING_KEY.get(next_stage)
    if timing_key and not app.config.get("TESTING"):
        delay = state["timing"].get(timing_key, 5)
        timer = threading.Timer(delay, _advance_lifecycle, args=(app, active_role))
        timer.daemon = True
        state["timers"].append(timer)
        timer.start()


def _run_lifecycle_sync(app, active_role):
    """Run the full lifecycle synchronously (for TESTING mode)."""
    state = _get_lifecycle_state(app)
    while state["lifecycle_active"] and state["current_stage"] != "kb_created":
        _advance_lifecycle(app, active_role)


# ---------------------------------------------------------------------------
# Fault Injection Middleware (refactored for runtime control)
# ---------------------------------------------------------------------------


def fault_middleware(f):
    """Middleware decorator that applies fault injection when enabled."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        from flask import current_app

        state = _get_fault_state(current_app)

        if not state["fault_active"]:
            return f(*args, **kwargs)

        fault_type = state["fault_type"]
        params = state["params"]
        active_role = current_app.config.get("ACTIVE_ROLE", SERVICE_ROLE)

        if fault_type == "memory-leak":
            chunk_size = params.get("chunk_size_kb", 100) * 1024
            state["memory_leak_store"].append(b"x" * chunk_size)
            state["memory_leak_bytes"] += chunk_size
            MEMORY_LEAK_BYTES.labels(service=active_role).set(state["memory_leak_bytes"])

        elif fault_type == "bad-deploy":
            error_rate = params.get("error_rate", 0.8)
            if random.random() < error_rate:
                ERROR_COUNT.labels(service=active_role, error_type="injected_bad_deploy").inc()
                return jsonify({
                    "error": "internal_server_error",
                    "detail": "Injected fault: bad-deploy",
                }), 500

        elif fault_type == "cascading-failure":
            error_rate = params.get("error_rate", 0.9)
            if random.random() < error_rate:
                ERROR_COUNT.labels(service=active_role, error_type="injected_cascade").inc()
                return jsonify({
                    "error": "service_unavailable",
                    "detail": "Injected fault: cascading-failure",
                }), 503

        elif fault_type == "scale-dependent":
            base_ms = params.get("base_latency_ms", 50)
            per_conn_ms = params.get("per_connection_ms", 200)
            try:
                active = ACTIVE_CONNECTIONS.labels(service=active_role)._value.get()
            except Exception:
                active = 1
            delay_s = (base_ms + per_conn_ms * max(active, 1)) / 1000.0
            if not current_app.config.get("TESTING"):
                time.sleep(delay_s)

        return f(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Metrics Instrumentation Decorator
# ---------------------------------------------------------------------------


def track_metrics(endpoint_name):
    """Decorator to track request metrics for an endpoint."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ACTIVE_CONNECTIONS.labels(service=SERVICE_ROLE).inc()
            start = time.time()
            try:
                result = f(*args, **kwargs)
                status = "200"
                if isinstance(result, tuple):
                    status = str(result[1])
                REQUEST_COUNT.labels(
                    service=SERVICE_ROLE,
                    method=request.method,
                    endpoint=endpoint_name,
                    status=status,
                ).inc()
                return result
            except Exception as e:
                ERROR_COUNT.labels(service=SERVICE_ROLE, error_type=type(e).__name__).inc()
                REQUEST_COUNT.labels(
                    service=SERVICE_ROLE,
                    method=request.method,
                    endpoint=endpoint_name,
                    status="500",
                ).inc()
                raise
            finally:
                duration = time.time() - start
                REQUEST_DURATION.labels(service=SERVICE_ROLE, endpoint=endpoint_name).observe(duration)
                ACTIVE_CONNECTIONS.labels(service=SERVICE_ROLE).dec()

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Flask Application Factory
# ---------------------------------------------------------------------------


def create_app(role=None):
    """Create and configure the Flask demo application for the given role."""
    app = Flask(__name__)
    active_role = role or SERVICE_ROLE
    app.config["ACTIVE_ROLE"] = active_role

    logger = logging.getLogger("demo")

    # ---- Common Endpoints ------------------------------------------------

    @app.route("/health")
    def health():
        state = _get_fault_state(app)
        return jsonify({
            "status": "healthy" if not state["fault_active"] else "degraded",
            "service": active_role,
            "fault_enabled": state["fault_active"],
            "fault_type": state["fault_type"] if state["fault_active"] else "none",
        })

    @app.route("/metrics")
    def metrics():
        return generate_latest(registry), 200, {"Content-Type": "text/plain; charset=utf-8"}

    # ---- Fault Control API (Task 1) --------------------------------------

    _register_fault_control_routes(app, active_role, logger)

    # ---- Lifecycle Demonstration API (Story 8-3) -------------------------

    _register_lifecycle_routes(app, active_role, logger)

    # ---- Role-Specific Endpoints -----------------------------------------

    if active_role == "api-gateway":
        _register_api_gateway_routes(app, logger)
    elif active_role == "backend":
        _register_backend_routes(app, logger)
    elif active_role == "database":
        _register_database_routes(app, logger)
    elif active_role == "worker":
        _register_worker_routes(app, logger)

    return app


# ---------------------------------------------------------------------------
# Fault Control API (Task 1)
# ---------------------------------------------------------------------------


def _register_fault_control_routes(app, active_role, logger):
    """Register fault injection control endpoints."""

    @app.route("/fault/inject", methods=["POST"])
    def fault_inject():
        data = request.get_json(force=True, silent=True) or {}
        fault_type = data.get("fault_type", "")

        if fault_type not in FAULT_TYPES:
            return jsonify({
                "error": "invalid_fault_type",
                "detail": f"Unknown fault type: {fault_type}",
                "available_types": list(FAULT_TYPES.keys()),
            }), 400

        params = data.get("params", {})
        merged_params = dict(FAULT_TYPES[fault_type]["default_params"])
        merged_params.update(params)

        state = _get_fault_state(app)

        # Clear previous fault's active gauge if overwriting
        if state["fault_active"] and state["fault_type"] in FAULT_TYPES:
            FAULT_INJECTION_ACTIVE.labels(
                service=active_role, fault_type=state["fault_type"]
            ).set(0)

        state["fault_active"] = True
        state["fault_type"] = fault_type
        state["params"] = merged_params
        state["started_at"] = datetime.now(timezone.utc).isoformat()

        # Update metrics
        FAULT_INJECTION_ACTIVE.labels(service=active_role, fault_type=fault_type).set(1)
        FAULT_INJECTION_TOTAL.labels(service=active_role, fault_type=fault_type).inc()

        logger.warning("Fault injected: type=%s, params=%s", fault_type, merged_params)

        return jsonify({
            "status": "injected",
            "fault_type": fault_type,
            "service": active_role,
            "params": merged_params,
        })

    @app.route("/fault/recover", methods=["POST"])
    def fault_recover():
        state = _get_fault_state(app)
        previous_type = state["fault_type"]
        was_active = state["fault_active"]

        # Clear fault state
        state["fault_active"] = False
        state["fault_type"] = "none"
        state["params"] = {}
        state["started_at"] = None
        state["memory_leak_store"].clear()
        state["memory_leak_bytes"] = 0

        # Clear metrics
        MEMORY_LEAK_BYTES.labels(service=active_role).set(0)
        if was_active and previous_type in FAULT_TYPES:
            FAULT_INJECTION_ACTIVE.labels(
                service=active_role, fault_type=previous_type
            ).set(0)

        logger.warning("Fault recovered: previous_type=%s", previous_type)

        return jsonify({
            "status": "recovered",
            "service": active_role,
            "cleared_fault": previous_type if was_active else "none",
        })

    @app.route("/fault/status", methods=["GET"])
    def fault_status():
        state = _get_fault_state(app)
        result = {
            "service": active_role,
            "fault_active": state["fault_active"],
            "fault_type": state["fault_type"],
            "started_at": state["started_at"],
            "params": state["params"],
            "memory_leak_bytes": state["memory_leak_bytes"],
        }
        if state["fault_active"] and state["fault_type"] in FAULT_TYPES:
            ft = FAULT_TYPES[state["fault_type"]]
            result["description"] = ft["description"]
            result["expected_beeper_response"] = ft["expected_beeper_response"]
        return jsonify(result)

    @app.route("/fault/types", methods=["GET"])
    def fault_types():
        types_list = []
        for ft_name, ft_info in FAULT_TYPES.items():
            types_list.append({
                "type": ft_name,
                "description": ft_info["description"],
                "default_params": ft_info["default_params"],
                "expected_beeper_response": ft_info["expected_beeper_response"],
            })
        return jsonify({"fault_types": types_list})


# ---------------------------------------------------------------------------
# Lifecycle Demonstration API (Story 8-3)
# ---------------------------------------------------------------------------


def _register_lifecycle_routes(app, active_role, logger):
    """Register lifecycle demonstration control endpoints."""

    @app.route("/lifecycle/start", methods=["POST"])
    def lifecycle_start():
        state = _get_lifecycle_state(app)

        if state["lifecycle_active"]:
            return jsonify({
                "error": "lifecycle_already_active",
                "detail": "A lifecycle demonstration is already running. "
                          "Reset it first with POST /lifecycle/reset.",
                "current_stage": state["current_stage"],
            }), 409

        data = request.get_json(force=True, silent=True) or {}
        fault_type = data.get("fault_type", "")

        if fault_type not in FAULT_TYPES:
            return jsonify({
                "error": "invalid_fault_type",
                "detail": f"Unknown fault type: {fault_type}",
                "available_types": list(FAULT_TYPES.keys()),
            }), 400

        trust_level = data.get("trust_level", 5)
        if not isinstance(trust_level, int) or trust_level < 1 or trust_level > 5:
            return jsonify({
                "error": "invalid_trust_level",
                "detail": "trust_level must be an integer between 1 and 5",
            }), 400
        custom_timing = data.get("timing", {})
        timing = dict(DEFAULT_LIFECYCLE_TIMING)
        timing.update(custom_timing)

        now = datetime.now(timezone.utc)

        # Initialize lifecycle state
        state["lifecycle_active"] = True
        state["current_stage"] = "fault_injected"
        state["fault_type"] = fault_type
        state["trust_level"] = trust_level
        state["timing"] = timing
        state["started_at"] = now.isoformat()
        state["stage_history"] = [
            {
                "stage": "healthy",
                "timestamp": now.isoformat(),
                "duration_ms": 0,
                "narrative": _get_narrative("healthy", fault_type, trust_level, 0),
            },
            {
                "stage": "fault_injected",
                "timestamp": now.isoformat(),
                "duration_ms": None,
                "narrative": _get_narrative("fault_injected", fault_type, trust_level, 0),
            },
        ]
        state["timers"] = []

        # Inject the fault using existing fault state
        fault_state = _get_fault_state(app)
        if fault_state["fault_active"] and fault_state["fault_type"] in FAULT_TYPES:
            FAULT_INJECTION_ACTIVE.labels(
                service=active_role, fault_type=fault_state["fault_type"]
            ).set(0)
        fault_params = dict(FAULT_TYPES[fault_type]["default_params"])
        fault_state["fault_active"] = True
        fault_state["fault_type"] = fault_type
        fault_state["params"] = fault_params
        fault_state["started_at"] = now.isoformat()
        FAULT_INJECTION_ACTIVE.labels(service=active_role, fault_type=fault_type).set(1)
        FAULT_INJECTION_TOTAL.labels(service=active_role, fault_type=fault_type).inc()

        # Clear all previous stage metrics before setting new one
        for stage in LIFECYCLE_STAGES:
            LIFECYCLE_STAGE.labels(service=active_role, stage=stage).set(0)
        LIFECYCLE_STAGE.labels(service=active_role, stage="fault_injected").set(1)
        LIFECYCLE_DURATION.labels(service=active_role).set(0)

        estimated = sum(timing.values())

        logger.info(
            "Lifecycle started: fault_type=%s, trust_level=%d, estimated=%ds",
            fault_type, trust_level, estimated,
        )

        # Capture initial stage for response before sync execution mutates state
        initial_stage = state["current_stage"]

        # In TESTING mode, run synchronously; otherwise schedule timer
        if app.config.get("TESTING"):
            _run_lifecycle_sync(app, active_role)
        else:
            delay = timing.get("detect_seconds", 8)
            timer = threading.Timer(delay, _advance_lifecycle, args=(app, active_role))
            timer.daemon = True
            state["timers"].append(timer)
            timer.start()

        return jsonify({
            "status": "started",
            "fault_type": fault_type,
            "trust_level": trust_level,
            "service": active_role,
            "current_stage": initial_stage,
            "estimated_duration_seconds": estimated,
        })

    @app.route("/lifecycle/status", methods=["GET"])
    def lifecycle_status():
        state = _get_lifecycle_state(app)

        total_elapsed_ms = 0
        if state["started_at"]:
            total_elapsed_ms = int(
                (datetime.now(timezone.utc) - datetime.fromisoformat(state["started_at"]))
                .total_seconds() * 1000
            )

        return jsonify({
            "service": active_role,
            "lifecycle_active": state["lifecycle_active"],
            "current_stage": state["current_stage"],
            "fault_type": state["fault_type"],
            "trust_level": state["trust_level"],
            "started_at": state["started_at"],
            "total_elapsed_ms": total_elapsed_ms,
            "stage_history": state["stage_history"],
        })

    @app.route("/lifecycle/reset", methods=["POST"])
    def lifecycle_reset():
        state = _get_lifecycle_state(app)
        previous_stage = state["current_stage"]

        # Cancel any pending timers
        for timer in state.get("timers", []):
            timer.cancel()

        # Clear lifecycle metrics
        for stage in LIFECYCLE_STAGES:
            LIFECYCLE_STAGE.labels(service=active_role, stage=stage).set(0)
        LIFECYCLE_DURATION.labels(service=active_role).set(0)

        # Recover any active faults
        fault_state = _get_fault_state(app)
        faults_cleared = fault_state["fault_active"]
        if faults_cleared:
            prev_type = fault_state["fault_type"]
            fault_state["fault_active"] = False
            fault_state["fault_type"] = "none"
            fault_state["params"] = {}
            fault_state["started_at"] = None
            fault_state["memory_leak_store"].clear()
            fault_state["memory_leak_bytes"] = 0
            MEMORY_LEAK_BYTES.labels(service=active_role).set(0)
            if prev_type in FAULT_TYPES:
                FAULT_INJECTION_ACTIVE.labels(
                    service=active_role, fault_type=prev_type
                ).set(0)

        # Reset lifecycle state
        new_state = _create_lifecycle_state()
        app.config["lifecycle_state"] = new_state

        logger.info("Lifecycle reset: previous_stage=%s", previous_stage)

        return jsonify({
            "status": "reset",
            "service": active_role,
            "previous_stage": previous_stage,
            "faults_cleared": faults_cleared,
        })

    @app.route("/lifecycle/timeline", methods=["GET"])
    def lifecycle_timeline():
        state = _get_lifecycle_state(app)

        total_duration_ms = 0
        if state["started_at"]:
            total_duration_ms = int(
                (datetime.now(timezone.utc) - datetime.fromisoformat(state["started_at"]))
                .total_seconds() * 1000
            )

        lifecycle_complete = (
            not state["lifecycle_active"]
            and state["current_stage"] == "kb_created"
        )

        return jsonify({
            "service": active_role,
            "lifecycle_complete": lifecycle_complete,
            "total_duration_ms": total_duration_ms,
            "fault_type": state["fault_type"],
            "trust_level": state["trust_level"],
            "stages": state["stage_history"],
        })


# ---------------------------------------------------------------------------
# API Gateway Role
# ---------------------------------------------------------------------------


def _register_api_gateway_routes(app, logger):
    """Register routes for the api-gateway role."""

    @app.route("/api/v1/orders", methods=["GET", "POST"])
    @track_metrics("/api/v1/orders")
    @fault_middleware
    def orders():
        if request.method == "POST":
            logger.info("Routing order creation to backend")
            return jsonify({
                "order_id": f"ord-{int(time.time())}",
                "status": "created",
                "routed_to": "backend",
            }), 201
        logger.info("Listing orders via gateway")
        return jsonify({
            "orders": [
                {"order_id": "ord-1001", "status": "completed", "amount": 49.99},
                {"order_id": "ord-1002", "status": "processing", "amount": 129.50},
                {"order_id": "ord-1003", "status": "pending", "amount": 25.00},
            ],
            "total": 3,
        })

    @app.route("/api/v1/health")
    @track_metrics("/api/v1/health")
    def api_health():
        return jsonify({
            "gateway": "healthy",
            "upstream_services": {
                "backend": "healthy",
                "database": "healthy",
                "worker": "healthy",
            },
        })


# ---------------------------------------------------------------------------
# Backend Role
# ---------------------------------------------------------------------------


def _register_backend_routes(app, logger):
    """Register routes for the backend role."""

    @app.route("/process", methods=["POST"])
    @track_metrics("/process")
    @fault_middleware
    def process():
        logger.info("Processing request")
        if not app.config.get("TESTING"):
            time.sleep(random.uniform(0.01, 0.05))
        return jsonify({
            "result": "processed",
            "processing_time_ms": random.randint(10, 50),
            "service": "backend",
        })


# ---------------------------------------------------------------------------
# Database Role
# ---------------------------------------------------------------------------


def _register_database_routes(app, logger):
    """Register routes for the database role."""

    _data_store = {
        "orders": [
            {"id": 1, "customer": "acme-corp", "amount": 49.99, "status": "completed"},
            {"id": 2, "customer": "globex", "amount": 129.50, "status": "processing"},
        ],
        "customers": [
            {"id": 1, "name": "acme-corp", "plan": "enterprise"},
            {"id": 2, "name": "globex", "plan": "startup"},
        ],
    }

    @app.route("/query", methods=["GET", "POST"])
    @track_metrics("/query")
    @fault_middleware
    def query():
        if not app.config.get("TESTING"):
            time.sleep(random.uniform(0.005, 0.02))
        table = request.args.get("table", "orders")
        data = _data_store.get(table, [])
        logger.info("Query on table=%s, rows=%d", table, len(data))
        return jsonify({
            "table": table,
            "rows": data,
            "count": len(data),
            "query_time_ms": random.randint(1, 15),
        })


# ---------------------------------------------------------------------------
# Worker Role
# ---------------------------------------------------------------------------


def _register_worker_routes(app, logger):
    """Register routes for the worker role."""

    _job_queue = [
        {"job_id": "job-001", "type": "report_generation", "status": "completed"},
        {"job_id": "job-002", "type": "data_sync", "status": "running"},
        {"job_id": "job-003", "type": "cleanup", "status": "queued"},
    ]

    @app.route("/jobs", methods=["GET"])
    @track_metrics("/jobs")
    @fault_middleware
    def jobs():
        logger.info("Job queue status: %d jobs", len(_job_queue))
        return jsonify({
            "jobs": _job_queue,
            "total": len(_job_queue),
            "running": sum(1 for j in _job_queue if j["status"] == "running"),
            "queued": sum(1 for j in _job_queue if j["status"] == "queued"),
        })


# ---------------------------------------------------------------------------
# Synthetic Traffic Generator
# ---------------------------------------------------------------------------


def _run_synthetic_traffic(app):
    """Background thread that generates synthetic traffic to self."""
    logger = logging.getLogger("demo.traffic")
    client = app.test_client()

    endpoints = {
        "api-gateway": ["/api/v1/orders", "/api/v1/health", "/health"],
        "backend": ["/process", "/health"],
        "database": ["/query", "/health"],
        "worker": ["/jobs", "/health"],
    }

    role_endpoints = endpoints.get(SERVICE_ROLE, ["/health"])

    while True:
        try:
            endpoint = random.choice(role_endpoints)
            if endpoint == "/process":
                client.post(endpoint, json={"data": "synthetic"})
            else:
                client.get(endpoint)
        except Exception:
            logger.warning("Synthetic traffic error")
        time.sleep(random.uniform(0.5, 2.0))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main():
    """Start the demo application server."""
    setup_logging()
    logger = logging.getLogger("demo")

    app = create_app()
    logger.info("Starting demo %s on port %d", SERVICE_ROLE, SERVICE_PORT)

    if SYNTHETIC_TRAFFIC:
        traffic_thread = threading.Thread(target=_run_synthetic_traffic, args=(app,), daemon=True)
        traffic_thread.start()
        logger.info("Synthetic traffic generator started")

    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False)


if __name__ == "__main__":
    main()
