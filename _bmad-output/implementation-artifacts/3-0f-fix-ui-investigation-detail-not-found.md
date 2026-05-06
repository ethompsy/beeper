# Story 3.0f: Fix UI Investigation Detail "Not Found"

Status: ready-for-dev

## Story

As a **user**,
I want to click on any investigation in the UI list and see its detail view,
So that I can review the investigation findings, RCA, and recommendations.

## Background

**Origin:** Story 3-0c walkthrough failure (2026-05-06). Clicking any investigation in the list gives "Investigation not found."

**Root cause:** `operator/src/api.rs:418` uses `Api::all(client)` for the detail endpoint. In kube-rs, `Api::all().get("name")` on a namespaced CRD fails with 404 because it doesn't know which namespace to query. `Api::all().list()` works (queries all namespaces), but `get()` does not.

## Acceptance Criteria

1. **Given** investigations exist in the `beeper` namespace
   **When** the user clicks an investigation in the list view
   **Then** the detail view loads with full investigation data (header, steps, findings, recommendations)

2. **Given** the operator API
   **When** `GET /api/v1/investigations/{id}` is called
   **Then** the investigation is found and returned with 200 (not 404)

## Tasks / Subtasks

- [ ] Task 1: Fix the detail endpoint to use namespaced API
  - [ ] 1.1 In `get_investigation()` at `operator/src/api.rs:414`, change `Api::all()` to `Api::namespaced()` using the operator's namespace
  - [ ] 1.2 Determine namespace source: use `BEEPER_DETECTION_NAMESPACE` env var (already available in ApiState or can be passed through)
  - [ ] 1.3 Apply same fix to any other endpoints that use `Api::all().get()` for investigations

- [ ] Task 2: Update tests
  - [ ] 2.1 Add test for detail endpoint returning investigation successfully
  - [ ] 2.2 Verify existing tests pass with the change

- [ ] Task 3: Verify
  - [ ] 3.1 `cargo test --lib` — all tests pass
  - [ ] 3.2 `cargo clippy` — clean

## Dev Notes

### Key Files

- `operator/src/api.rs:414-475` — `get_investigation()` handler (BUG: uses `Api::all()`)
- `operator/src/api.rs:327` — `list_investigations()` (also uses `Api::all()` but works for list)
- `operator/src/api.rs` — `ApiState` struct (check if namespace is already stored)

### The Bug

```rust
// Line 418 — BROKEN for namespaced resources
let investigations_api: Api<Investigation> = Api::all((*state.client).clone());
// Api::all().get("name") doesn't know which namespace → 404

// Fix:
let investigations_api: Api<Investigation> = Api::namespaced((*state.client).clone(), &namespace);
```

### Pattern

The `list_investigations` endpoint also uses `Api::all()` but it works because `list()` queries across all namespaces. Only `get()` breaks. However, for consistency, both should probably use the same approach.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
