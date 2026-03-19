"""
Beeper Demo Application Server.

A multi-role Flask HTTP server that serves as all four demo microservices
(api-gateway, backend, database, worker) based on the SERVICE_ROLE env var.

Each role exposes Prometheus metrics, structured JSON logging, health endpoints,
and configurable fault injection hooks (disabled by default, activated in story 8-2).
"""

import json
import logging
import os
import random
import threading
import time
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

# ---------------------------------------------------------------------------
# Fault Injection Hooks (dormant — activated by story 8-2)
# ---------------------------------------------------------------------------

_memory_leak_store: list = []


def fault_middleware(f):
    """Middleware decorator that applies fault injection when enabled."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not FAULT_ENABLED:
            return f(*args, **kwargs)

        if FAULT_TYPE == "memory-leak":
            # Gradually consume memory
            _memory_leak_store.append(b"x" * 1024 * 100)  # 100KB per request

        if FAULT_TYPE == "error-rate":
            # Randomly return 500 errors
            if random.random() < 0.5:
                ERROR_COUNT.labels(service=SERVICE_ROLE, error_type="injected").inc()
                return jsonify({"error": "internal_server_error", "detail": "Injected fault"}), 500

        if FAULT_TYPE == "latency":
            # Add artificial latency
            time.sleep(random.uniform(1.0, 3.0))

        if FAULT_TYPE == "resource-exhaustion":
            # Simulate high CPU via busy loop
            end = time.time() + 0.1
            while time.time() < end:
                pass

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

    logger = logging.getLogger("demo")

    # ---- Common Endpoints ------------------------------------------------

    @app.route("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": active_role,
            "fault_enabled": FAULT_ENABLED,
            "fault_type": FAULT_TYPE if FAULT_ENABLED else "none",
        })

    @app.route("/metrics")
    def metrics():
        return generate_latest(registry), 200, {"Content-Type": "text/plain; charset=utf-8"}

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
        except Exception as e:
            logger.warning(f"Synthetic traffic error: {e}")
        time.sleep(random.uniform(0.5, 2.0))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main():
    """Start the demo application server."""
    setup_logging()
    logger = logging.getLogger("demo")

    app = create_app()
    logger.info(f"Starting demo {SERVICE_ROLE} on port {SERVICE_PORT}")

    if SYNTHETIC_TRAFFIC:
        traffic_thread = threading.Thread(target=_run_synthetic_traffic, args=(app,), daemon=True)
        traffic_thread.start()
        logger.info("Synthetic traffic generator started")

    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False)


if __name__ == "__main__":
    main()
