---
title: 'Fix Demo Failure Detection Pipeline'
slug: 'fix-demo-failure-detection'
created: '2026-04-03'
status: 'completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - rust (operator - axum, kube-rs, tokio, serde_json)
  - python (investigator - anthropic, qdrant-client, kubernetes)
  - python (ui - flask, socketio)
  - kubernetes (kind cluster, helm, CRDs)
  - qdrant (vector DB, payload-only collections)
  - opentelemetry (collector, OTLP HTTP, flagd fault injection)
  - prometheus (metrics, PromQL SLO queries)
files_to_modify:
  - demo/otel-demo-values.yaml
  - demo/k8s/slo-cart.yaml
  - demo/k8s/slo-checkout.yaml
  - demo/k8s/slo-frontend.yaml
  - demo/k8s/slo-payment.yaml
  - demo/k8s/slo-productcatalog.yaml
  - operator/src/slo/mod.rs
  - operator/src/notifications/outbox.rs
  - operator/src/ingestion/otlp.rs
  - demo/tests/test_slo_manifests.py
  - demo/README.md
  - Makefile
code_patterns:
  - axum Json extractor rejects non-application/json (returns 415)
  - Qdrant payload-only collection created with "vectors":{} but upsert needs "vector":{} per point
  - OTel Collector otlphttp exporter defaults to protobuf, needs explicit encoding:json
  - SLO engine queries Prometheus directly every 5s via reqwest HTTP
  - Detection consumer reads from IngestionBuffer via mpsc channel in async loop
  - Log detector extracts service from labels priority: service > service_name > app > job > namespace
  - Error levels matched case-insensitive: error, err, fatal, critical, panic
  - Investigation CRDs created in BEEPER_DETECTION_NAMESPACE (set to Helm Release.Namespace = "beeper")
test_patterns:
  - Rust: tokio::test for async, #[test] for sync, co-located in #[cfg(test)] modules
  - Mocking: wiremock for HTTP, tower::ServiceExt::oneshot for axum handlers
  - Shared state: Arc<IngestionBuffer> pattern in handler tests
  - Edge cases: NaN, zero counts, buffer overflow, missing optional fields
  - Test deps: tokio-test, wiremock, tower, http-body-util
  - Run with: cargo test (no Makefile target, standard cargo)
---

# Tech-Spec: Fix Demo Failure Detection Pipeline

**Created:** 2026-04-03

## Overview

### Problem Statement

When faults are injected in the OTel demo (e.g. `make demo-fault FAULT=payment-failure`), Beeper neither detects the failures nor starts investigations. Both detection paths are completely broken:

1. **Log error rate detection (primary path):** OTel Collector sends OTLP logs to `/v1/logs` but receives HTTP 415 — every log is dropped. The detection engine receives zero data and cannot detect error rate spikes from faults.
2. **SLO burn rate detection (secondary path):** All 5 SLO definitions have wrong service names and/or wrong metric names. Every PromQL query returns empty data. Burn rate alerts never fire.
3. **SLO data persistence:** Qdrant upsert fails with "missing field vector" for SLO snapshots.

### Solution

Fix 3 distinct bugs that collectively break the pipeline:
1. Fix OTLP content-type mismatch (HTTP 415) so error logs flow into the detection engine
2. Correct 4 SLO definitions to match actual Prometheus data; remove payment SLO (no suitable metric)
3. Fix Qdrant SLO snapshot upsert to include empty vector field

### Scope

**In Scope:**
- Fix OTLP content-type handling (collector config: add `encoding: json`)
- Correct SLO definitions for cart, checkout, frontend, productcatalog (service names + metric names)
- Remove payment SLO (no server-side request metric available; payment errors detected via log path)
- Fix Qdrant `slo_snapshots` upsert payload (add `"vector": {}`)
- Add warmup documentation to Makefile demo targets
- Verify end-to-end: fault injection -> detection -> investigation CRD created

**Out of Scope:**
- Prometheus remote_write pipeline (intentionally disabled per otel-demo-values.yaml comments)
- Protobuf support in OTLP handler (follow-up work for production)
- Investigator agent execution fixes
- New SLO features or dashboard work
- Exposing detection tuning params (MIN_SAMPLES, etc.) in Helm values

## Context for Development

### Codebase Patterns

- **OTLP Handler** (`operator/src/ingestion/otlp.rs:136`): Uses axum `Json(request)` extractor which automatically validates `Content-Type: application/json`. Non-JSON requests get 415. No middleware — validation is in the extractor.
- **OTel Collector** (`demo/otel-demo-values.yaml:69-70`): `otlphttp/beeper` exporter sends to `http://beeper-operator-ingestion.beeper.svc:9090` but doesn't specify encoding, so defaults to protobuf.
- **Log Detection** (`operator/src/detection/logs.rs:164-173`): Extracts service name from labels in priority order: `service` > `service_name` > `app` > `job` > `namespace`. Falls back to "unknown". Error levels: error, err, fatal, critical, panic (case-insensitive).
- **Detection Consumer** (`operator/src/detection/consumer.rs:120-131`): Reads from IngestionBuffer async channel. Routes Metric vs Log to appropriate detectors. Creates Investigation CRDs when anomalies detected.
- **Investigation Namespace**: `BEEPER_DETECTION_NAMESPACE` set to `{{ .Release.Namespace }}` in Helm = `beeper`.
- **EWMA Config**: `MIN_SAMPLES=10` (warmup), `THRESHOLD=3.0` (stddev), `COOLDOWN_SECS=600`, `WINDOW_SECS=300` (5-min sliding window, 1-min buckets). All use code defaults — no Helm overrides.
- **SLO Engine** (`operator/src/slo/mod.rs:174-216`): Writes snapshots to Qdrant `slo_snapshots` collection. Collection created as payload-only (`"vectors": {}`), but upsert missing `"vector": {}` per point.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `demo/otel-demo-values.yaml:66-77` | OTel Collector config — needs `encoding: json` on otlphttp/beeper exporter |
| `demo/k8s/slo-cart.yaml` | Cart SLO — service_name wrong (`cartservice` -> `cart`), metric wrong (needs `http_server_request_duration_seconds_count`) |
| `demo/k8s/slo-checkout.yaml` | Checkout SLO — service_name wrong (`checkoutservice` -> `checkout`), metric correct |
| `demo/k8s/slo-frontend.yaml` | Frontend SLO — service_name correct, metric wrong (needs `http_server_duration_milliseconds_count`), label name correct (`http_status_code`) |
| `demo/k8s/slo-payment.yaml` | Payment SLO — no suitable server metric exists, remove |
| `demo/k8s/slo-productcatalog.yaml` | ProductCatalog SLO — service_name wrong (`productcatalogservice` -> `product-catalog`), metric correct |
| `operator/src/slo/mod.rs:181-188` | Qdrant upsert — missing `"vector": {}` in point object |
| `operator/src/notifications/outbox.rs:172-178` | Qdrant upsert — identical missing `"vector": {}` bug |
| `operator/src/ingestion/otlp.rs` | OTLP handler — fix misleading comment at line 8 |
| `demo/tests/test_slo_manifests.py:10-16` | SLO manifest tests — `SLO_FILES` list needs updated service names, payment entry removed |
| `demo/README.md:108` | File tree listing — remove `slo-payment.yaml` reference |
| `operator/src/detection/logs.rs` | Log error detector — reference for understanding detection flow |
| `operator/src/detection/consumer.rs` | Detection consumer — reference for Investigation CRD creation |
| `operator/src/slo/burn_rate.rs` | Burn rate alerter — creates Investigation CRDs when SLO burns |
| `helm/beeper/templates/operator-deployment.yaml` | Helm env vars — detection config reference |
| `Makefile:29-35, 186-209` | Demo targets — add warmup documentation |

### Technical Decisions

- **OTLP encoding**: Use `encoding: json` in collector config rather than adding protobuf support to the Rust handler. Ships immediately; protobuf support is follow-up. Note: JSON encoding increases payload size ~2-3x vs protobuf.
- **Payment SLO**: Remove for now. Payment service (Node.js) emits no server-side request metrics. `app_payment_transactions_total` has no error/status labels. Payment errors will be detected via log error rate spikes (primary detection path).
- **Detection warmup**: Keep `MIN_SAMPLES=10` (10 minutes with 1-minute buckets). Document in Makefile output so demo operators know to wait.

### Verified Prometheus Metric Mapping (Live Data)

| Service | `service_name` in Prometheus | Metric Name | Good Selector | Total Selector |
|---------|------------------------------|-------------|---------------|----------------|
| checkout | `checkout` | `rpc_server_duration_milliseconds_count` | `{service_name="checkout",rpc_grpc_status_code="0"}` | `{service_name="checkout"}` |
| product-catalog | `product-catalog` | `rpc_server_duration_milliseconds_count` | `{service_name="product-catalog",rpc_grpc_status_code="0"}` | `{service_name="product-catalog"}` |
| cart | `cart` | `http_server_request_duration_seconds_count` | `{service_name="cart",http_response_status_code=~"2.."}` | `{service_name="cart"}` |
| frontend | `frontend` | `http_server_duration_milliseconds_count` | `{service_name="frontend",http_status_code=~"[23].."}` | `{service_name="frontend"}` |
| payment | `payment` | **None suitable** | N/A — rely on log detection | N/A |

## Implementation Plan

### Tasks

- [x] **Task 1: Fix OTLP collector encoding (unblocks log detection)**
  - File: `demo/otel-demo-values.yaml`
  - Action: Add `encoding: json` to the `otlphttp/beeper` exporter config so the OTel Collector sends JSON instead of protobuf
  - Change the exporter block from:
    ```yaml
    otlphttp/beeper:
      endpoint: http://beeper-operator-ingestion.beeper.svc:9090
      tls:
        insecure: true
    ```
    to:
    ```yaml
    otlphttp/beeper:
      endpoint: http://beeper-operator-ingestion.beeper.svc:9090
      encoding: json
      tls:
        insecure: true
    ```
  - Notes: The `otlphttp` exporter defaults to protobuf. Beeper's handler (`otlp.rs:136`) uses axum's `Json` extractor which only accepts `application/json`. Adding `encoding: json` tells the collector to send JSON payloads.

- [x] **Task 2: Fix Qdrant upsert in SLO snapshots AND notification outbox (unblocks persistence)**
  - Files: `operator/src/slo/mod.rs`, `operator/src/notifications/outbox.rs`
  - Action: Add `"vector": {}` to the point object in both `write_snapshot()` (mod.rs:181-188) and `write_notification()` (outbox.rs:172-178)
  - Change in **`operator/src/slo/mod.rs`** from:
    ```rust
    let body = serde_json::json!({
        "points": [
            {
                "id": point_id,
                "payload": snapshot
            }
        ]
    });
    ```
    to:
    ```rust
    let body = serde_json::json!({
        "points": [
            {
                "id": point_id,
                "vector": {},
                "payload": snapshot
            }
        ]
    });
    ```
  - Apply **identical fix** in **`operator/src/notifications/outbox.rs`** at line 172-178 — same pattern, add `"vector": {}` between `"id"` and `"payload"`.
  - Notes: Both collections (`slo_snapshots` and `notification_outbox`) are created as payload-only with `"vectors": {}`, but Qdrant's REST API still requires the `vector` field in upsert point objects. An empty object `{}` satisfies this for payload-only collections. The outbox worker is actively running (`main.rs:265`) so this fix is needed for notifications to persist.

- [x] **Task 3: Fix checkout SLO definition**
  - File: `demo/k8s/slo-checkout.yaml`
  - Action: Change `service` from `"checkoutservice"` to `"checkout"`. Update selectors to use `service_name="checkout"`.
  - Exact changes:
    - Line 9: `service: "checkoutservice"` -> `service: "checkout"`
    - Line 13: `good_selector: '{service_name="checkoutservice",rpc_grpc_status_code="0"}'` -> `good_selector: '{service_name="checkout",rpc_grpc_status_code="0"}'`
    - Line 14: `total_selector: '{service_name="checkoutservice"}'` -> `total_selector: '{service_name="checkout"}'`
  - Notes: Metric name `rpc_server_duration_milliseconds_count` is correct. Only service name needs fixing.

- [x] **Task 4: Fix product catalog SLO definition**
  - File: `demo/k8s/slo-productcatalog.yaml`
  - Action: Change `service` from `"productcatalogservice"` to `"product-catalog"`. Update selectors.
  - Exact changes:
    - Line 9: `service: "productcatalogservice"` -> `service: "product-catalog"`
    - Line 13: `good_selector: '{service_name="productcatalogservice",rpc_grpc_status_code="0"}'` -> `good_selector: '{service_name="product-catalog",rpc_grpc_status_code="0"}'`
    - Line 14: `total_selector: '{service_name="productcatalogservice"}'` -> `total_selector: '{service_name="product-catalog"}'`
  - Notes: Metric name `rpc_server_duration_milliseconds_count` is correct. Only service name needs fixing.

- [x] **Task 5: Fix cart SLO definition (service name + metric)**
  - File: `demo/k8s/slo-cart.yaml`
  - Action: Change service name and switch to HTTP metric. Full spec replacement:
    ```yaml
    spec:
      service: "cart"
      sli:
        type: availability
        metric: "http_server_request_duration_seconds_count"
        good_selector: '{service_name="cart",http_response_status_code=~"2.."}'
        total_selector: '{service_name="cart"}'
    ```
  - Notes: Cart is a C#/.NET service using HTTP server instrumentation (not gRPC). Uses new OTel semantic convention label `http_response_status_code`.

- [x] **Task 6: Fix frontend SLO definition (metric name)**
  - File: `demo/k8s/slo-frontend.yaml`
  - Action: Change metric name. Service name `frontend` is already correct. Full spec replacement:
    ```yaml
    spec:
      service: "frontend"
      sli:
        type: availability
        metric: "http_server_duration_milliseconds_count"
        good_selector: '{service_name="frontend",http_status_code=~"[23].."}'
        total_selector: '{service_name="frontend"}'
    ```
  - Notes: Frontend is Node.js. Uses `http_server_duration_milliseconds_count` (not `http_server_request_duration_seconds_count`). Uses old OTel semantic convention label `http_status_code` (not `http_response_status_code`). The `good_selector` pattern `[23]..` matches 2xx and 3xx status codes.

- [x] **Task 7: Remove payment SLO and all references**
  - Files: `demo/k8s/slo-payment.yaml`, `Makefile`, `demo/README.md`
  - Action: Delete `demo/k8s/slo-payment.yaml`. The payment service (Node.js) does not emit any server-side request metrics suitable for an availability SLI. `app_payment_transactions_total` has no error/status labels. Payment errors will be detected via the OTLP log error rate detection path (Task 1 unblocks this).
  - Also remove from Makefile `demo-deploy` target — delete line 142:
    ```
    kubectl apply -f $(DEMO_DIR)/k8s/slo-payment.yaml
    ```
  - Also update `demo/README.md` — remove `slo-payment.yaml` from the file tree listing at line 108.

- [x] **Task 8: Add warmup documentation to Makefile**
  - File: `Makefile`
  - Action: Add warmup reminder to `demo-up` completion message and `demo-fault` output.
  - For `demo-up` (after line 34), add:
    ```
    @echo "  NOTE: Detection needs ~10 minutes of log data flowing before"
    @echo "        anomalies can be detected. Wait before injecting faults."
    ```
  - For `demo-fault` (after line 209 "Monitor with: make demo-fault-status"), add:
    ```
    @echo "    NOTE: If operator was recently restarted, detection needs"
    @echo "          ~10 minutes of log data flowing before anomalies are detected."
    ```

- [x] **Task 9: Fix misleading comment in OTLP handler**
  - File: `operator/src/ingestion/otlp.rs`
  - Action: Fix the incorrect module doc comment at line 8.
  - Change from:
    ```rust
    //! The `otlphttp` exporter in OTel Collector sends JSON by default to
    ```
    to:
    ```rust
    //! The `otlphttp` exporter in OTel Collector sends protobuf by default;
    //! Beeper's collector config sets `encoding: json` so it sends JSON to
    ```
  - Notes: The original comment was factually wrong — the default is protobuf, not JSON. This caused confusion during investigation.

- [x] **Task 10: Update SLO manifest test suite**
  - File: `demo/tests/test_slo_manifests.py`
  - Action: Update `SLO_FILES` list to match corrected service names and remove payment entry.
  - Change from:
    ```python
    SLO_FILES = [
        ("slo-checkout.yaml", "checkoutservice", 0.999),
        ("slo-cart.yaml", "cartservice", 0.999),
        ("slo-payment.yaml", "paymentservice", 0.9995),
        ("slo-frontend.yaml", "frontend", 0.995),
        ("slo-productcatalog.yaml", "productcatalogservice", 0.999),
    ]
    ```
    to:
    ```python
    SLO_FILES = [
        ("slo-checkout.yaml", "checkout", 0.999),
        ("slo-cart.yaml", "cart", 0.999),
        ("slo-frontend.yaml", "frontend", 0.995),
        ("slo-productcatalog.yaml", "product-catalog", 0.999),
    ]
    ```
  - Notes: Payment entry removed (file deleted in Task 7). Service names updated to match live Prometheus `service_name` values. All 11 test methods x 4 files = 44 parametrized test cases should pass.

- [x] **Task 11: Rebuild, redeploy, and verify**
  - Action: Rebuild operator Docker image (Qdrant fixes are in Rust code), reload into kind, redeploy via Helm. Apply updated SLO YAMLs. Verify all fixes.
  - Steps:
    1. `cd operator && cargo test` — verify existing tests still pass with mod.rs and outbox.rs changes
    2. `cd demo && python -m pytest tests/test_slo_manifests.py -v` — verify SLO manifest tests pass with updated values
    3. `docker build -t beeper/operator:dev ./operator` — rebuild operator image
    4. `kind load docker-image beeper/operator:dev --name beeper-demo` — load into kind
    5. `helm upgrade beeper ./helm/beeper --namespace beeper` — redeploy operator with new image
    6. `kubectl delete servicelevel otel-payment-slo -n otel-demo` — remove payment SLO from cluster (uses resource name, not file reference, since file is already deleted in Task 7)
    7. `kubectl apply -f demo/k8s/` — apply corrected SLO definitions
    8. `helm upgrade otel-demo open-telemetry/opentelemetry-demo -n otel-demo -f demo/otel-demo-values.yaml` — redeploy collector with JSON encoding
    9. Wait 10+ minutes for detection warmup
    10. Run verification checks (see Acceptance Criteria)

### Acceptance Criteria

- [ ] **AC-1:** Given the OTel Collector is running with the updated config, when it exports logs to Beeper, then the operator logs show `"Successfully buffered OTLP log entries"` (no HTTP 415 errors in collector logs).

- [ ] **AC-2:** Given the operator has been running for >10 minutes with the load generator active (warmup complete, no prior cooldown active), when `make demo-fault FAULT=payment-failure` is executed, then an Investigation CRD is created in the `beeper` namespace within 5 minutes (detected via log error rate spike).

- [ ] **AC-3:** Given the corrected SLO definitions are applied, when the SLO engine runs its polling cycle, then operator logs show actual compliance values for checkout, product-catalog, cart, and frontend (no more "SLO query returned no data" messages for these services).

- [ ] **AC-4:** Given the Qdrant vector fix is deployed, when the SLO engine writes a snapshot, then the write succeeds without "missing field vector" warnings in operator logs.

- [ ] **AC-5:** Given all fixes are deployed and warmed up (no prior cooldown active for cart service), when `make demo-fault FAULT=cart-failure` is executed, then an Investigation CRD is created (verifying a second fault type triggers detection).

- [ ] **AC-6:** Given the payment SLO YAML is deleted, when `kubectl get servicelevels -n otel-demo` is run, then `otel-payment-slo` is not listed (and no SLO "no data" logs reference `paymentservice`).

- [ ] **AC-7:** Given `make demo-up` completes, when the user reads the terminal output, then a warmup reminder is visible telling them to wait ~10 minutes before injecting faults.

- [ ] **AC-8:** Given the SLO manifest test suite runs (`python -m pytest demo/tests/test_slo_manifests.py`), when all tasks are complete, then all parametrized tests pass with the updated service names and without the payment SLO entry.

## Review Notes

- Adversarial review completed
- Findings: 7 total, 6 fixed, 1 skipped (noise)
- Resolution approach: auto-fix
- F1 (label inconsistency): Documented with comments in SLO YAMLs — reflects verified live Prometheus data
- F2 (2xx vs 2xx+3xx): Documented with comments — cart API has no redirects, frontend does
- F3 (payment fault help text): Changed demo-up example to cart-failure
- F4 (README missing payment note): Added note about log detection for payment
- F5 (warmup wording): Clarified applies after demo-up or restart
- F6 (no vector test): Added regression tests in both mod.rs and outbox.rs
- F7 (YAML placement): Skipped — noise, syntactically correct

## Additional Context

### Dependencies

- **Docker**: Required to rebuild the operator image with the Qdrant fix
- **kind**: Required to load the rebuilt image into the demo cluster
- **Helm 3.x**: Required to upgrade the Beeper and OTel demo releases
- **Running demo cluster**: `kind get clusters` must show `beeper-demo`
- **Active load generator**: The OTel demo load generator pod must be running to produce baseline traffic for detection warmup

### Testing Strategy

**Unit Tests (automated):**
- Run `cargo test` in `operator/` after the `mod.rs` and `outbox.rs` changes. All existing tests must pass. The `test_qdrant_writer_point_id_deterministic` and other SLO tests are unaffected by the vector field addition (they test different code paths).
- Run `python -m pytest demo/tests/test_slo_manifests.py -v` after updating service names and removing payment. All 44 parametrized tests (11 methods x 4 files) must pass.

**Integration Verification (manual, post-deploy):**
1. Check OTel Collector logs: `kubectl logs -n otel-demo daemonset/otel-collector-agent --tail=20` — no 415 errors
2. Check operator ingestion: `kubectl logs -n beeper deploy/beeper-operator --since=60s | grep "buffered OTLP"` — entries appearing
3. Check SLO engine: `kubectl logs -n beeper deploy/beeper-operator --since=60s | grep -v "no data"` — compliance values logged
4. Check Qdrant writes: `kubectl logs -n beeper deploy/beeper-operator --since=60s | grep "missing field"` — no matches

**End-to-End Fault Test (manual, after 10min warmup):**
1. `make demo-fault FAULT=payment-failure`
2. Wait 2-5 minutes
3. `kubectl get investigations -n beeper` — at least one Investigation exists
4. `make demo-recover`
5. `make demo-fault FAULT=cart-failure`
6. Wait 2-5 minutes
7. `kubectl get investigations -n beeper` — additional Investigation created

### Notes

**Evidence from live system (2026-04-03):**
- OTel Collector logs confirm continuous 415 errors: `"Exporting failed. Dropping data."` with `HTTP Status Code 415`
- SLO engine logs confirm: `"SLO query returned no data — metric may not exist in Prometheus"` for ALL 5 services
- Qdrant logs confirm: `"missing field 'vector'"` on every SLO snapshot write
- Detection enabled by default (code default `true`, no Helm override needed)

**Known limitations:**
- Payment service has no SLO monitoring — relies entirely on log error rate detection
- OTLP uses JSON encoding (2-3x larger than protobuf) — acceptable for demo, follow-up for production
- Detection tuning params (MIN_SAMPLES, THRESHOLD, etc.) not exposed in Helm values — all use code defaults
- `BEEPER_DETECTION_COOLDOWN_SECS=600` means the same anomaly won't re-trigger for 10 minutes after first detection

**Follow-up work (out of scope):**
- Add protobuf support to OTLP handler for production efficiency
- Expose detection config params in Helm values for per-deployment tuning
- Find or create a suitable SLI metric for the payment service
