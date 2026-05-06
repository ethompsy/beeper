# Story 3.0h: Fix Investigator RBAC Permissions

Status: ready-for-dev

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

- [ ] Task 1: Identify all K8s resource types the investigator queries
  - [ ] 1.1 Search investigator Python code for K8s API calls
  - [ ] 1.2 List all resource types and verbs needed (likely: get, list for events, pods, services, deployments, HPAs, replicasets)

- [ ] Task 2: Update Helm RBAC templates
  - [ ] 2.1 Find the investigator Role/ClusterRole template in `helm/beeper/templates/`
  - [ ] 2.2 Add read-only rules for all identified resource types
  - [ ] 2.3 Keep permissions minimal (read-only, specific namespaces)

- [ ] Task 3: Verify
  - [ ] 3.1 `helm template` renders correct RBAC
  - [ ] 3.2 No existing tests should break (RBAC is Helm-only)

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

### Debug Log References

### Completion Notes List

### File List
