# Story 1.2: Qdrant Infrastructure

Status: done

## Story

As an **Admin**,
I want Qdrant deployed with the correct collection schemas,
So that investigators and the UI have a vector database ready for KB operations.

## Acceptance Criteria

### AC1: Qdrant StatefulSet Deployment
**Given** the Helm chart includes Qdrant configuration
**When** I deploy Beeper via Helm
**Then** a Qdrant StatefulSet is created with persistent storage
**And** the Qdrant REST API is accessible on port 6333
**And** the Qdrant gRPC API is accessible on port 6334

### AC2: Investigations Collection Schema
**Given** Qdrant is running
**When** the collection initialization runs
**Then** the `investigations` collection exists with schema:
- `investigation_id` (keyword) - unique identifier
- `status` (keyword) - investigation status
- `started_at` (datetime) - ISO 8601 timestamp
- `service` (keyword) - affected service name
- `embedding` (vector) - semantic embedding for similarity search

### AC3: Knowledge Collection Schema
**Given** Qdrant is running
**When** the collection initialization runs
**Then** the `knowledge` collection exists with schema:
- `entry_id` (keyword) - unique identifier
- `entry_type` (keyword) - one of: investigation, runbook, correction
- `service` (keyword) - related service name
- `created_at` (datetime) - ISO 8601 timestamp
- `embedding` (vector) - semantic embedding for similarity search

### AC4: Local Development Seeding
**Given** Qdrant is running locally (via docker-compose)
**When** I run `scripts/seed-kb.sh`
**Then** sample KB entries are created for local development testing
**And** the script is idempotent (can be run multiple times safely)

## Tasks / Subtasks

- [x] Task 1: Create Qdrant StatefulSet Helm template (AC: #1)
  - [x] 1.1: Create `helm/beeper/templates/qdrant-statefulset.yaml` with StatefulSet definition
  - [x] 1.2: Configure persistent volume claim template (10Gi default, configurable)
  - [x] 1.3: Configure ports: 6333 (REST), 6334 (gRPC)
  - [x] 1.4: Add resource limits and requests (memory: 1Gi, cpu: 500m defaults)
  - [x] 1.5: Add readiness and liveness probes using /healthz endpoint
  - [x] 1.6: Add security context (non-root user)

- [x] Task 2: Create Qdrant Service Helm template (AC: #1)
  - [x] 2.1: Create `helm/beeper/templates/qdrant-service.yaml` for ClusterIP service
  - [x] 2.2: Expose ports 6333 (REST) and 6334 (gRPC)
  - [x] 2.3: Add conditional rendering based on `qdrant.enabled` value

- [x] Task 3: Update Helm values for Qdrant configuration (AC: #1)
  - [x] 3.1: Expand `qdrant` section in `values.yaml` with image, resources, service config
  - [x] 3.2: Add `qdrant.image.repository` (default: qdrant/qdrant)
  - [x] 3.3: Add `qdrant.image.tag` (default: latest or pinned version)
  - [x] 3.4: Add `qdrant.resources` section with limits/requests
  - [x] 3.5: Add `qdrant.service.type` (default: ClusterIP)
  - [x] 3.6: Update `values-dev.yaml` with development-appropriate settings

- [x] Task 4: Create collection initialization script (AC: #2, #3)
  - [x] 4.1: Create `scripts/init-collections.py` Python script
  - [x] 4.2: Define `investigations` collection with payload schema and vector config
  - [x] 4.3: Define `knowledge` collection with payload schema and vector config
  - [x] 4.4: Make script idempotent (check if collection exists before creating)
  - [x] 4.5: Configure vector dimension (1536 for OpenAI embeddings, configurable)
  - [x] 4.6: Configure distance metric (Cosine similarity)
  - [x] 4.7: Add payload indexes for keyword fields (investigation_id, status, entry_type, service)

- [x] Task 5: Create KB seeding script (AC: #4)
  - [x] 5.1: Create `scripts/seed-kb.sh` bash wrapper script
  - [x] 5.2: Create `scripts/seed_kb.py` Python script with sample data
  - [x] 5.3: Add sample runbook entries (3-5 examples for common issues)
  - [x] 5.4: Add sample investigation entries (2-3 completed examples)
  - [x] 5.5: Generate placeholder embeddings (zeros or random for dev)
  - [x] 5.6: Make script idempotent using upsert operations

- [x] Task 6: Update docker-compose for local Qdrant (AC: #1, #4)
  - [x] 6.1: Verify Qdrant service configuration in docker-compose.yaml
  - [x] 6.2: Add environment variable for gRPC port (QDRANT__SERVICE__GRPC_PORT=6334)
  - [x] 6.3: Document collection initialization in README

- [x] Task 7: Create Qdrant client utilities (AC: #2, #3)
  - [x] 7.1: Create `investigator/beeper_investigator/kb/__init__.py`
  - [x] 7.2: Create `investigator/beeper_investigator/kb/client.py` with Qdrant client wrapper
  - [x] 7.3: Create `investigator/beeper_investigator/kb/schemas.py` with Pydantic models
  - [x] 7.4: Add connection configuration (host, port from environment)
  - [x] 7.5: Add collection name constants matching schema

- [x] Task 8: Add tests for Qdrant infrastructure (AC: #1, #2, #3)
  - [x] 8.1: Create `investigator/tests/test_kb_client.py` with unit tests
  - [x] 8.2: Add integration test for collection creation (requires running Qdrant)
  - [x] 8.3: Add test for schema validation using Pydantic models
  - [x] 8.4: Mark integration tests with pytest marker for CI skip

- [x] Task 9: Documentation and validation (AC: #1, #2, #3, #4)
  - [x] 9.1: Update root README.md with Qdrant setup instructions
  - [x] 9.2: Run `helm lint ./helm/beeper` to validate chart
  - [x] 9.3: Test local deployment with `docker-compose up -d`
  - [x] 9.4: Run init-collections.py and verify collections exist
  - [x] 9.5: Run seed-kb.sh and verify sample data

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Vector Database Decision]

Qdrant was chosen over pgvector for:
- Horizontal scaling built-in
- Purpose-built vector performance
- Excellent metadata filtering
- Rust-based (aligns with operator choice)

**Collection Naming:** Use `snake_case` per architecture standards (`investigations`, `knowledge`)

**Field Naming:** All payload fields use `snake_case` (`investigation_id`, `created_at`, `confidence_level`)

### Qdrant Configuration Best Practices

**Source:** [Qdrant Documentation](https://qdrant.tech/documentation/concepts/collections/)

- **Distance Metric:** Use Cosine similarity (implemented as dot-product over normalized vectors)
- **Vector Dimension:** 1536 for OpenAI text-embedding-ada-002 or similar models
- **Payload Indexes:** Create keyword indexes for filterable fields to enable efficient metadata filtering
- **Quantization:** Consider int8 quantization for production to reduce memory by 4x (optional for MVP)

### Helm Chart Patterns

**Source:** [qdrant-helm GitHub](https://github.com/qdrant/qdrant-helm)

StatefulSet is the correct K8s resource for Qdrant because:
- Stable network identities
- Stable persistent storage
- Ordered, graceful deployment and scaling

**Health Probes:**
```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 6333
  initialDelaySeconds: 5
  periodSeconds: 10
livenessProbe:
  httpGet:
    path: /healthz
    port: 6333
  initialDelaySeconds: 15
  periodSeconds: 20
```

### Collection Schema Details

**investigations collection:**
```python
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client.create_collection(
    collection_name="investigations",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# Create payload indexes for filtering
client.create_payload_index(
    collection_name="investigations",
    field_name="investigation_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
client.create_payload_index(
    collection_name="investigations",
    field_name="status",
    field_schema=PayloadSchemaType.KEYWORD,
)
client.create_payload_index(
    collection_name="investigations",
    field_name="service",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

**knowledge collection:**
```python
client.create_collection(
    collection_name="knowledge",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

client.create_payload_index(
    collection_name="knowledge",
    field_name="entry_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
client.create_payload_index(
    collection_name="knowledge",
    field_name="entry_type",
    field_schema=PayloadSchemaType.KEYWORD,
)
client.create_payload_index(
    collection_name="knowledge",
    field_name="service",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

### Environment Variables

```bash
QDRANT_HOST=localhost  # or qdrant.beeper.svc.cluster.local in K8s
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
```

### Project Structure Notes

Files to create/modify align with architecture:
```
helm/beeper/templates/
├── qdrant-statefulset.yaml  # NEW
├── qdrant-service.yaml      # NEW

investigator/beeper_investigator/
├── kb/                      # NEW directory
│   ├── __init__.py
│   ├── client.py            # Qdrant client wrapper
│   └── schemas.py           # Pydantic models

scripts/
├── init-collections.py      # NEW
├── seed-kb.sh               # NEW
└── seed_kb.py               # NEW
```

### Dependencies

This story depends on:
- Story 1.1 (Project Scaffolding) - COMPLETED

This story blocks:
- Story 1.3 (K8s Operator Scaffold) - needs Qdrant for status tracking
- Story 2.1 (KB Wiki Interface) - needs knowledge collection
- Story 3.2 (Investigator Agent Scaffold) - needs investigations collection

### Testing Strategy

**Unit Tests:**
- Pydantic model validation
- Client configuration parsing

**Integration Tests (marked for local only):**
- Collection creation/deletion
- Point insertion/retrieval
- Payload filtering queries

Mark integration tests with:
```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("QDRANT_HOST"), reason="Qdrant not available")
```

### References

- [Source: architecture.md#Vector Database Decision]
- [Source: architecture.md#Data Architecture]
- [Source: architecture.md#Qdrant Naming]
- [Source: architecture.md#Implementation Patterns & Consistency Rules]
- [Source: epics.md#Story 1.2: Qdrant Infrastructure]
- [Qdrant Collections Documentation](https://qdrant.tech/documentation/concepts/collections/)
- [Qdrant Helm Chart](https://github.com/qdrant/qdrant-helm)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Fixed Pydantic deprecation warnings (class Config → model_config = ConfigDict)
- Added pytest marker registration for integration tests
- Auto-fixed import sorting with ruff

### Completion Notes List

- ✅ Created Qdrant StatefulSet Helm template with persistent storage, health probes, security context
- ✅ Created Qdrant Service (ClusterIP) and headless service for StatefulSet DNS
- ✅ Expanded Helm values with image config, resources, collection settings
- ✅ Created init-collections.py with idempotent collection creation and payload indexes
- ✅ Created seed-kb.sh + seed_kb.py with 4 sample runbooks and 3 sample investigations
- ✅ Pinned Qdrant image version to v1.12.0 in docker-compose and Helm
- ✅ Created KB client module with KBClient, schemas (InvestigationEntry, KnowledgeEntry)
- ✅ Added 18 unit tests for schemas and client, 3 integration tests (skipped without Qdrant)
- ✅ Updated README with Qdrant setup instructions
- ✅ All linting passes, all tests pass, helm lint passes

### Code Review Fixes (2026-02-09)

- ✅ [HIGH] Added `started_at` datetime payload index to investigations collection per AC#2
- ✅ [HIGH] Added `created_at` datetime payload index to knowledge collection per AC#3
- ✅ [HIGH] Updated File List to include modified Dockerfiles (investigator/Dockerfile, operator/Dockerfile)
- ✅ [MEDIUM] Fixed placeholder embeddings to use entry_id-based seeds for unique per-entry vectors
- ✅ [MEDIUM] Added thread-safe double-check locking pattern to get_kb_client() singleton
- ✅ [MEDIUM] Added __version__ export to kb module
- ✅ [MEDIUM] Added test_get_kb_client_thread_safe test for singleton thread safety
- ✅ All 19 unit tests pass, 3 integration tests skipped (require Qdrant), ruff lint passes

### File List

**New Files:**
- helm/beeper/templates/qdrant-statefulset.yaml
- helm/beeper/templates/qdrant-service.yaml
- investigator/beeper_investigator/kb/__init__.py
- investigator/beeper_investigator/kb/client.py
- investigator/beeper_investigator/kb/schemas.py
- scripts/init-collections.py
- scripts/seed-kb.sh
- scripts/seed_kb.py
- investigator/tests/test_kb_client.py

**Modified Files:**
- helm/beeper/values.yaml
- helm/beeper/values-dev.yaml
- docker-compose.yaml
- investigator/pyproject.toml
- investigator/Dockerfile
- operator/Dockerfile
- README.md

## Change Log

- 2026-02-03: Story created and ready for development
- 2026-02-04: Story implementation completed - all 9 tasks with 39 subtasks finished
- 2026-02-09: Code review completed - fixed 3 HIGH and 4 MEDIUM issues (datetime indexes, thread safety, File List accuracy)
