# Story 1.9: Investigation CRD & Pod Spawning

Status: ready-for-dev

## Story

As **Beeper**,
I want to spawn Investigator pods for detected conditions,
So that each investigation runs in isolation with dedicated resources.

## Acceptance Criteria

### AC1: Investigation CR Lifecycle
**Given** the Investigation CRD is defined
**When** the operator detects a suspicious condition
**Then** it creates an Investigation custom resource
**And** the Investigation status tracks: `pending`, `running`, `completed`, `failed`

### AC2: Investigator Job Spawning
**Given** an Investigation CR is created
**When** the operator reconciles
**Then** a K8s Job is spawned with the investigator container (FR38)
**And** the Job has access to: Qdrant, LLM API, source credentials
**And** the Job is labeled with `investigation_id` for tracking

### AC3: Job Completion Handling
**Given** an investigator Job completes
**When** the operator reconciles
**Then** the Investigation CR status is updated
**And** the Job is cleaned up according to retention policy

### AC4: Job Failure Handling
**Given** an investigator Job fails
**When** the operator reconciles
**Then** the Investigation CR shows failure status with error details
**And** retry policy is applied if configured

## Tasks / Subtasks

- [ ] Task 1: Implement Investigation status updates (AC: #1)
  - [ ] 1.1: Add function to update Investigation status using kube-rs PATCH
  - [ ] 1.2: Implement `set_phase(Pending)` when Investigation is newly created
  - [ ] 1.3: Store `started_at` timestamp when transitioning from Pending to Running
  - [ ] 1.4: Store `completed_at` timestamp when transitioning to Completed/Failed

- [ ] Task 2: Implement Job spawning logic (AC: #2)
  - [ ] 2.1: Create `InvestigatorJobBuilder` struct for configuring Job spec
  - [ ] 2.2: Configure Job with investigator container image from values.yaml
  - [ ] 2.3: Mount LLM credentials Secret as environment variable (`BEEPER_LLM_API_KEY`)
  - [ ] 2.4: Mount source credentials Secrets if configured
  - [ ] 2.5: Set environment variables: `INVESTIGATION_ID`, `BEEPER_LLM_PROVIDER`, `BEEPER_LLM_MODEL`, `QDRANT_URL`
  - [ ] 2.6: Add labels: `app.kubernetes.io/component=investigator`, `beeper.dev/investigation-id`
  - [ ] 2.7: Set Job `backoffLimit` and `activeDeadlineSeconds` from config

- [ ] Task 3: Implement reconciler Job lifecycle management (AC: #2, #3, #4)
  - [ ] 3.1: In reconcile Pending phase: create Job and transition to Running
  - [ ] 3.2: In reconcile Running phase: watch Job status via `jobs.batch` API
  - [ ] 3.3: Detect Job completion (succeeded condition) and transition to Completed
  - [ ] 3.4: Detect Job failure and transition to Failed with error message from Job

- [ ] Task 4: Implement Job cleanup (AC: #3)
  - [ ] 4.1: Add `ttlSecondsAfterFinished` to Job spec for automatic cleanup
  - [ ] 4.2: Update Investigation CR status before Job is garbage collected
  - [ ] 4.3: Store Job pod logs reference in Investigation status (optional)

- [ ] Task 5: Add Helm configuration for investigator (AC: #2)
  - [ ] 5.1: Add `investigator` section to values.yaml with image, resources, service account
  - [ ] 5.2: Create investigator ServiceAccount with RBAC for Qdrant access
  - [ ] 5.3: Document investigator Job configuration in values.yaml comments

- [ ] Task 6: Update investigator main.py for Job execution (AC: #2)
  - [ ] 6.1: Read `INVESTIGATION_ID` from environment variable
  - [ ] 6.2: Initialize LlmClient from environment variables
  - [ ] 6.3: Initialize Qdrant KbClient from environment
  - [ ] 6.4: Log structured JSON with `investigation_id` context
  - [ ] 6.5: Exit with appropriate exit code (0=success, 1=failure)

- [ ] Task 7: Add integration tests (AC: #1, #2, #3, #4)
  - [ ] 7.1: Test Investigation status transition from None to Pending
  - [ ] 7.2: Test Job creation with correct labels and environment
  - [ ] 7.3: Test Job completion updates Investigation to Completed
  - [ ] 7.4: Test Job failure updates Investigation to Failed with error

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Communication Patterns]

Investigation state machine:
```
pending → started → investigating → [correlating|querying_kb|reasoning] → completed
                                                                      ↘ failed
```

**Component Boundaries (from architecture.md):**
```
Operator (Rust) --[K8s Job spawn]--> Investigator (Python)
Investigator --[REST/HTTP]--> Qdrant (KB writes)
```

**Source:** [architecture.md - K8s Resources]

- `Job: beeper-investigator-{id}` - Spawned per investigation
- Job is owned by Investigation CR for garbage collection

**Source:** [architecture.md - Naming Patterns]

- JSON fields: `snake_case` everywhere
- Use `#[serde(rename_all = "snake_case")]` on Rust structs
- Labels: `app.kubernetes.io/component`, `beeper.dev/investigation-id`

### Previous Story Learnings (1-8)

**Source:** [1-8-llm-provider-configuration.md - Code Review Record]

Key patterns to reuse:
1. **Secret reading:** `read_secret_key()` function in `operator/src/llm.rs` - reuse for source credentials
2. **Error handling:** Map K8s API errors to user-friendly messages
3. **Configuration:** LLM config already in values.yaml - investigator will read via env vars
4. **Health status:** LlmManager pattern for checking configuration validity

**Code Review Fixes from 1-8:**
- Use helper functions for error handling to avoid duplication
- Health status should say "Configured:" not "Connected to" unless live testing
- Model validation in both Rust and Python

### Existing CRD Implementation

**Investigation CRD already exists at:** `operator/src/crds/investigation.rs`

Current structure:
```rust
pub struct InvestigationSpec {
    pub condition: String,
    pub service: String,
    pub severity: Severity,
    pub triggered_at: Option<String>,
}

pub struct InvestigationStatus {
    pub phase: Option<InvestigationPhase>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub job_name: Option<String>,
    pub error: Option<String>,
}

pub enum InvestigationPhase {
    Pending, Running, Completed, Failed,
}
```

### Existing Controller Stub

**Investigation controller at:** `operator/src/controllers/investigation.rs`

Current reconcile function has TODO placeholders for each phase. The story must implement:
1. Status updates (currently just logs)
2. Job spawning (currently TODO)
3. Job monitoring (currently TODO)

### Job Specification Pattern

**Based on kube-rs Job API:**

```rust
use k8s_openapi::api::batch::v1::{Job, JobSpec};
use k8s_openapi::api::core::v1::{Container, EnvVar, PodSpec, PodTemplateSpec};

fn build_investigator_job(investigation: &Investigation, config: &InvestigatorConfig) -> Job {
    Job {
        metadata: ObjectMeta {
            name: Some(format!("inv-{}", investigation_id)),
            namespace: investigation.namespace(),
            labels: Some(BTreeMap::from([
                ("app.kubernetes.io/component".to_string(), "investigator".to_string()),
                ("beeper.dev/investigation-id".to_string(), investigation_id.to_string()),
            ])),
            owner_references: Some(vec![/* Investigation as owner */]),
            ..Default::default()
        },
        spec: Some(JobSpec {
            backoff_limit: Some(config.backoff_limit),
            ttl_seconds_after_finished: Some(config.ttl_after_finished),
            template: PodTemplateSpec {
                spec: Some(PodSpec {
                    containers: vec![Container {
                        name: "investigator".to_string(),
                        image: Some(config.image.clone()),
                        env: Some(vec![
                            EnvVar { name: "INVESTIGATION_ID".to_string(), value: Some(investigation_id.to_string()), ..Default::default() },
                            // ... more env vars
                        ]),
                        ..Default::default()
                    }],
                    restart_policy: Some("Never".to_string()),
                    ..Default::default()
                }),
                ..Default::default()
            },
            ..Default::default()
        }),
        ..Default::default()
    }
}
```

### Environment Variables for Investigator

| Variable | Source | Description |
|----------|--------|-------------|
| `INVESTIGATION_ID` | Job spec | Unique ID for this investigation |
| `BEEPER_LLM_PROVIDER` | ConfigMap/values | LLM provider (anthropic, openai, etc.) |
| `BEEPER_LLM_MODEL` | ConfigMap/values | Model identifier |
| `BEEPER_LLM_API_KEY` | Secret mount | API key for LLM provider |
| `BEEPER_QDRANT_URL` | ConfigMap/values | Qdrant service URL |
| `BEEPER_QDRANT_API_KEY` | Secret mount (optional) | Qdrant API key if enabled |

### Helm values.yaml Structure

Add to existing values.yaml:
```yaml
# Investigator Job configuration
investigator:
  image:
    repository: beeper/investigator
    tag: ""  # Defaults to Chart appVersion
    pullPolicy: IfNotPresent
  resources:
    limits:
      cpu: 1000m
      memory: 512Mi
    requests:
      cpu: 200m
      memory: 256Mi
  # Job behavior
  backoffLimit: 2
  ttlSecondsAfterFinished: 3600  # 1 hour
  activeDeadlineSeconds: 1800   # 30 minutes max
  serviceAccount:
    create: true
    name: ""
```

### Testing Strategy

**Unit Tests (Rust):**
- `InvestigatorJobBuilder` creates correct Job spec
- Environment variables are properly set
- Owner references are correct
- Labels match expected values

**Integration Tests (Rust):**
- Mock K8s client: create Investigation → verify Job created
- Mock K8s client: Job completes → Investigation status updated
- Mock K8s client: Job fails → Investigation shows error

**Unit Tests (Python):**
- `main.py` reads environment variables correctly
- Structured logging includes `investigation_id`
- Exit codes for success/failure

### Project Structure Notes

**New files to create:**
```
operator/src/
├── investigator_job.rs     # New: Job building logic
helm/beeper/
├── templates/
│   └── investigator-rbac.yaml  # New: ServiceAccount, Role for investigator
```

**Files to modify:**
```
operator/src/
├── lib.rs                  # Export investigator_job module
├── controllers/
│   └── investigation.rs    # Implement reconcile logic
helm/beeper/
├── values.yaml             # Add investigator section
investigator/
├── beeper_investigator/
│   └── main.py             # Update for Job execution
```

### References

- [Source: architecture.md#Communication Patterns]
- [Source: architecture.md#K8s Resources]
- [Source: architecture.md#Naming Patterns]
- [Source: epics.md#Story 1.9: Investigation CRD & Pod Spawning]
- [Source: 1-8-llm-provider-configuration.md#Code Review Record]
- [kube-rs Documentation](https://kube.rs/)
- [K8s Job API Reference](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/job-v1/)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-02-12: Story created by create-story workflow - ready for development
