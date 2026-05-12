# Story 3.0h: Fix Investigator RBAC Permissions

Status: done

## Story

As a **developer**,
I want the investigator pods to have sufficient RBAC permissions to query Kubernetes resources,
So that investigations can gather K8s signals (events, services, HPAs) for higher-quality RCA.

## Background

**Origin:** Story 3-0c walkthrough failure (2026-05-06). Investigator logs show `Failed to list events in namespace beeper: Forbidden` for multiple resource types. Previously documented as a "known limitation" in Story 3-0b, but it meaningfully degrades RCA quality.

## Acceptance Criteria

1. **Given** an investigator Job runs in the cluster
   **When** it attempts to query K8s resources for signal gathering
   **Then** it can read events, services, pods, HPAs, and deployments in the target namespace

2. **Given** the investigator ClusterRole/Role
   **When** inspected
   **Then** it has read-only permissions for the resource types the investigator queries

3. **Given** the RBAC changes
   **When** deployed via Helm
   **Then** `helm template` renders the correct RBAC rules

## Tasks / Subtasks

- [x] Task 1: Identify all K8s resource types the investigator queries
  - [x] 1.1 Search investigator Python code for K8s API calls
  - [x] 1.2 List all resource types and verbs needed (likely: get, list for events, pods, services, deployments, HPAs, replicasets)

- [x] Task 2: Update Helm RBAC templates
  - [x] 2.1 Find the investigator Role/ClusterRole template in `helm/beeper/templates/`
  - [x] 2.2 Add read-only rules for all identified resource types
  - [x] 2.3 Keep permissions minimal (read-only, specific namespaces)

- [x] Task 3: Verify
  - [x] 3.1 `helm template` renders correct RBAC
  - [x] 3.2 No existing tests should break (RBAC is Helm-only)

## Dev Notes

### Key Files

- `helm/beeper/templates/` — Look for investigator ServiceAccount, Role, ClusterRole, RoleBinding templates
- `investigator/beeper_investigator/steps/` — Signal gathering steps that query K8s
- `investigator/beeper_investigator/sources/` — K8s source client

### Known Forbidden Resources (from 3-0c logs)

- Events (v1)
- Services (v1)
- HorizontalPodAutoscalers (autoscaling)
- Pods (v1) — may already work
- Deployments (apps/v1)

### Security Principle

Grant **read-only** access only. Investigator should never modify cluster state. Scope to specific namespaces where otel-demo services run (beeper, otel-demo).

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
N/A — Helm-only change, no runtime debugging needed.

### Completion Notes List
- Searched all investigator Python code across 5 files for K8s API calls
- Found 12 resource types queried across 6 API groups (core/v1, apps/v1, autoscaling/v1, networking.k8s.io/v1, cert-manager.io/v1, beeper.dev/v1)
- Previously granted: secrets, configmaps, investigations/status
- Added read-only (get, list) permissions for: events, services, pods, endpoints, deployments, horizontalpodautoscalers, ingresses, certificates, servicelevels, repositories
- Namespaced permissions via Role; cluster-scoped namespace read via ClusterRole (sandbox detection)
- `helm template` renders correctly with all RBAC rules (ServiceAccount, ClusterRole, ClusterRoleBinding, Role, RoleBinding)
- Full test suite run: 0 regressions (11 pre-existing failures on main, unrelated to RBAC)

### Senior Developer Review (AI)
- **Review Date:** 2026-05-12
- **Review Outcome:** Changes Requested
- **Action Items:**
  - [x] [HIGH] Add ClusterRole + ClusterRoleBinding for `namespaces:get` — sandbox_executor.py:87 `read_namespace()` is cluster-scoped
  - [x] [MED] Fix stale Role description comment — said "Qdrant and status" but role now covers signal gathering
  - [x] [MED] Fix completion notes claiming "5 API groups" when there are 6
  - [ ] [MED] No automated Helm unit tests for RBAC rule validation (deferred — no helm-unittest in project)

### File List
- `helm/beeper/templates/investigator-rbac.yaml` — Added 6 new namespaced RBAC rules, 1 ClusterRole for namespace read, updated Role description comment
