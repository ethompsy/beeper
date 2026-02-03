---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: complete
completedAt: '2026-02-03'
inputDocuments:
  - prd.md
  - architecture.md
summary:
  epics: 6
  stories: 39
  frs_covered: 47
  nfrs_addressed: 17
---

# Beeper - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Beeper, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Investigation Management (FR1-FR12):**
- FR1: Beeper can continuously monitor incoming log and metric streams for anomalous patterns
- FR2: Beeper can spawn a dedicated Investigator for each detected suspicious condition
- FR3: Investigator can assess whether a detected condition has customer impact
- FR4: Investigator can correlate signals across multiple architectural layers (infrastructure, platform, application, data)
- FR5: Investigator can query the Knowledge Base for similar past incidents
- FR6: Investigator can build on prior research when investigating recurring conditions
- FR7: Investigator can generate a root cause hypothesis with an explicit confidence level
- FR8: Investigator can recommend resolution actions based on investigation findings
- FR9: Investigator can document its investigation process and findings to the Knowledge Base
- FR10: SRE can observe an Investigator's reasoning process in real-time
- FR11: SRE can confirm or reject an Investigator's resolution recommendation
- FR12: SRE can mark an investigation as resolved with outcome confirmation

**Knowledge Base (FR13-FR23):**
- FR13: SRE Lead can import existing runbooks into the Knowledge Base
- FR14: SRE can search the Knowledge Base using natural language queries (semantic search)
- FR15: SRE can search the Knowledge Base using structured filters (service, error type, date range)
- FR16: SRE can view investigation documentation in a human-readable wiki format
- FR17: SRE Lead can directly edit Knowledge Base entries
- FR18: SRE Lead can provide conversational corrections to Beeper ("update this entry to reflect X")
- FR19: Beeper can revise Knowledge Base entries based on conversational corrections
- FR20: Beeper can learn from the diff between its documentation and human corrections
- FR21: SRE can view version history of any Knowledge Base entry
- FR22: SRE can compare versions of a Knowledge Base entry (diff view)
- FR23: Beeper can publish entries directly as trust is established (graduated authoring)

**Observability Integration (FR24-FR30):**
- FR24: Admin can configure Prometheus as a metrics data source
- FR25: Admin can configure Loki as a log data source
- FR26: Admin can provide read-only credentials for each data source
- FR27: Beeper can receive pushed log and metric data via streaming connections
- FR28: Admin can view the status of all configured data sources
- FR29: Admin can view errors and warnings for misconfigured data sources
- FR30: Beeper can ingest data without adding latency to the monitored systems

**User Interface (FR31-FR36):**
- FR31: SRE can view a list of active investigations
- FR32: SRE can view the real-time reasoning of any active Investigator (investigation pane)
- FR33: SRE can view recommended resolutions with confidence levels
- FR34: SRE can navigate from an investigation to related Knowledge Base entries
- FR35: SRE Lead can view MTTR trends over time
- FR36: SRE can access the Knowledge Base wiki interface

**Deployment & Operations (FR37-FR41):**
- FR37: Admin can deploy Beeper as a Kubernetes operator
- FR38: Beeper can spawn Investigator pods within the Kubernetes cluster
- FR39: Admin can configure Beeper via Kubernetes custom resources
- FR40: Admin can view Beeper's operational health status
- FR41: Beeper can operate with all data remaining on customer premises (self-hosted)

**LLM Management (FR42-FR47):**
- FR42: Admin can configure which LLM provider Beeper uses
- FR43: Beeper can use lightweight models for initial screening tasks
- FR44: Beeper can escalate to more powerful models for deep RCA
- FR45: Beeper can cache and memoize results to avoid redundant LLM calls
- FR46: Admin can set spending caps or rate limits for LLM usage
- FR47: Beeper can surface environments with excessive investigation costs to the Admin

### Non-Functional Requirements

**Performance:**
- NFR-P1: Anomaly detection latency - Seconds from occurrence to detection
- NFR-P2: Investigation pane updates - Real-time streaming
- NFR-P3: KB search response - Sub-second
- NFR-P4: Data ingestion overhead - Zero added latency to monitored systems

**Security:**
- NFR-S1: Data residency - All data remains on customer premises (MVP)
- NFR-S2: Credential storage - Use K8s secrets or external secrets operator
- NFR-S3: Access model - Read-only access to all data sources
- NFR-S4: UI access control (MVP) - Internal network only (VPN/private network)
- NFR-S5: UI access control (v1.1) - Role-based access (admin vs user) [DEFERRED]

**Reliability:**
- NFR-R1: Component independence - Each component operates independently where possible
- NFR-R2: KB unavailability handling - Investigator buffers findings locally until KB returns
- NFR-R3: Graceful degradation - SREs can use traditional tools if Beeper fails
- NFR-R4: Investigation durability - Completed investigations persisted to KB

**Integration:**
- NFR-I1: Observability stack compatibility - Prometheus and Loki for MVP
- NFR-I2: LLM provider flexibility - Configurable provider (Claude API default)
- NFR-I3: K8s native deployment - Operator pattern with CRDs
- NFR-I4: Streaming data ingestion - Push/stream protocols (not polling)

### Additional Requirements

**From Architecture - Technology Stack:**
- Rust + kube-rs for K8s operator (memory-safe, async, production-ready)
- Python 3.11+ for investigators and UI (rapid development, LLM ecosystem)
- Qdrant for vector database (semantic search, metadata filtering)
- Flask + HTMX + SSE for MVP UI (simple, no JavaScript complexity)
- LiteLLM for LLM client (provider flexibility, streaming support)
- OpenAPI 3.1 specification for all APIs
- RFC 7807 Problem Details for error responses

**From Architecture - Project Structure:**
- Monorepo structure with separate deployable components
- `operator/` - Rust K8s operator
- `investigator/` - Python investigator agent
- `ui/` - Flask web UI
- `openapi/` - Shared API specifications
- `helm/` - Helm chart for deployment

**From Architecture - Implementation Patterns:**
- snake_case for all JSON fields, API params, Qdrant fields
- ISO 8601 UTC for all timestamps
- Structured JSON logging with required fields (timestamp, level, component, message)
- API versioning: `/api/v1/` base path
- Plural nouns for resources (`/investigations`, `/sources`)

**From Architecture - Data Architecture:**
- Qdrant collections: `investigations` (operational state) + `knowledge` (permanent KB)
- Read-your-writes consistency for investigator seeing own writes
- Metadata filtering for structured queries

**From Architecture - Deployment:**
- Helm chart for single-command install
- Docker multi-stage builds for all components
- GitHub Actions for CI/CD
- K8s resources: Deployment (operator, ui), Job (investigator), StatefulSet (qdrant)

**From Architecture - Critical Path:**
- OpenAPI spec must be defined first (enables Rust/Python client generation)
- Qdrant schema must be defined before investigator can write
- Operator CRDs must be defined before investigator spawning works

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 3 | Monitor streams for anomalies |
| FR2 | Epic 3 | Spawn dedicated Investigator |
| FR3 | Epic 3 | Assess customer impact |
| FR4 | Epic 3 | Correlate across architectural layers |
| FR5 | Epic 3 | Query KB for similar incidents |
| FR6 | Epic 3 | Build on prior research |
| FR7 | Epic 3 | Generate RCA hypothesis with confidence |
| FR8 | Epic 3 | Recommend resolution actions |
| FR9 | Epic 3 | Document to KB |
| FR10 | Epic 4 | Observe investigator reasoning in real-time |
| FR11 | Epic 4 | Confirm or reject resolution recommendation |
| FR12 | Epic 4 | Mark investigation resolved with outcome |
| FR13 | Epic 2 | Import existing runbooks |
| FR14 | Epic 2 | Search KB using natural language |
| FR15 | Epic 2 | Search KB using structured filters |
| FR16 | Epic 2 | View entries in wiki format |
| FR17 | Epic 2 | Directly edit KB entries |
| FR18 | Epic 5 | Provide conversational corrections |
| FR19 | Epic 5 | Beeper revises based on corrections |
| FR20 | Epic 5 | Learn from diff between original and correction |
| FR21 | Epic 2 | View version history |
| FR22 | Epic 2 | Compare versions (diff view) |
| FR23 | Epic 5 | Publish directly as trust is established |
| FR24 | Epic 1 | Configure Prometheus data source |
| FR25 | Epic 1 | Configure Loki data source |
| FR26 | Epic 1 | Provide read-only credentials |
| FR27 | Epic 1 | Receive pushed log/metric data |
| FR28 | Epic 1 | View status of data sources |
| FR29 | Epic 1 | View errors/warnings for misconfig |
| FR30 | Epic 1 | Ingest without adding latency |
| FR31 | Epic 4 | View list of active investigations |
| FR32 | Epic 4 | View real-time reasoning (investigation pane) |
| FR33 | Epic 4 | View recommendations with confidence |
| FR34 | Epic 4 | Navigate to related KB entries |
| FR35 | Epic 6 | View MTTR trends over time |
| FR36 | Epic 2 | Access KB wiki interface |
| FR37 | Epic 1 | Deploy Beeper as K8s operator |
| FR38 | Epic 1 | Spawn Investigator pods in cluster |
| FR39 | Epic 1 | Configure via K8s custom resources |
| FR40 | Epic 1 | View operational health status |
| FR41 | Epic 1 | Self-hosted operation |
| FR42 | Epic 1 | Configure LLM provider |
| FR43 | Epic 3 | Use lightweight models for screening |
| FR44 | Epic 3 | Escalate to powerful models for RCA |
| FR45 | Epic 3 | Cache/memoize to avoid redundant calls |
| FR46 | Epic 6 | Set spending caps/rate limits |
| FR47 | Epic 6 | Surface environments with excessive costs |

## Epic List

### Epic 1: Platform Foundation
Admin can deploy Beeper to a K8s cluster, connect it to Prometheus/Loki, and verify everything is operational.

**FRs covered:** FR24-30, FR37-42

### Epic 2: Knowledge Base
SRE team has a functional knowledge base wiki where they can import runbooks, search, view, edit, and track version history.

**FRs covered:** FR13-17, FR21-22, FR36

### Epic 3: Investigation Engine
Beeper can detect anomalies in logs/metrics, spawn investigators, correlate signals across layers, generate root cause hypotheses, and document findings to the KB.

**FRs covered:** FR1-9, FR43-45

### Epic 4: Investigation Experience
SREs can observe Beeper's investigations in real-time, view recommendations with confidence levels, confirm/reject resolutions, and mark investigations complete.

**FRs covered:** FR10-12, FR31-34

### Epic 5: Living Knowledge
KB becomes a self-improving system where SREs can provide conversational corrections, Beeper learns from feedback, and trust enables direct publishing.

**FRs covered:** FR18-20, FR23

### Epic 6: Operations & Insights
Admins can control LLM costs with spending caps, see which environments drive excessive costs, and team leads can view MTTR trends.

**FRs covered:** FR35, FR46-47

---

## Epic 1: Platform Foundation

Admin can deploy Beeper to a K8s cluster, connect it to Prometheus/Loki, and verify everything is operational.

### Story 1.1: Project Scaffolding

As an **Admin/Developer**,
I want the Beeper project structure and CI pipeline established,
So that I have a foundation for building all components.

**Acceptance Criteria:**

**Given** the Beeper repository is initialized
**When** I clone the repository
**Then** I see the monorepo structure matching the architecture:
```
beeper/
├── operator/           # Rust K8s operator (Cargo.toml)
├── investigator/       # Python investigator (pyproject.toml)
├── ui/                 # Flask web UI (pyproject.toml)
├── openapi/            # OpenAPI spec scaffold
├── helm/               # Helm chart scaffold
├── scripts/            # Dev scripts
└── docker-compose.yaml # Local dev stack
```
**And** each component has a minimal "hello world" entry point

**Given** the CI pipeline is configured
**When** I push to main branch
**Then** GitHub Actions runs lint and test jobs for all components
**And** Docker images can be built for each component

**Given** the OpenAPI specification exists
**When** I view `openapi/beeper-api.yaml`
**Then** I see the API structure with placeholder endpoints for:
- `/api/v1/investigations`
- `/api/v1/knowledge`
- `/api/v1/sources`
**And** the spec follows OpenAPI 3.1 with RFC 7807 error schemas

### Story 1.2: Qdrant Infrastructure

As an **Admin**,
I want Qdrant deployed with the correct collection schemas,
So that investigators and the UI have a vector database ready for KB operations.

**Acceptance Criteria:**

**Given** the Helm chart includes Qdrant
**When** I deploy Beeper via Helm
**Then** Qdrant StatefulSet is created with persistent storage
**And** the `investigations` collection exists with schema:
- `investigation_id` (keyword)
- `status` (keyword)
- `started_at` (datetime)
- `service` (keyword)
- `embedding` (vector)
**And** the `knowledge` collection exists with schema:
- `entry_id` (keyword)
- `entry_type` (keyword: investigation, runbook, correction)
- `service` (keyword)
- `created_at` (datetime)
- `embedding` (vector)

**Given** Qdrant is running
**When** I run `scripts/seed-kb.sh`
**Then** sample KB entries are created for local development testing

### Story 1.3: K8s Operator Scaffold

As an **Admin**,
I want to deploy Beeper as a Kubernetes operator,
So that Beeper runs natively in my K8s cluster with proper RBAC.

**Acceptance Criteria:**

**Given** the Helm chart is installed
**When** I run `helm install beeper ./helm/beeper`
**Then** the `beeper-operator` Deployment is created
**And** a ServiceAccount with appropriate RBAC permissions exists
**And** the operator pod starts successfully and logs "Beeper operator started"

**Given** the operator is running
**When** I check operator health
**Then** the operator exposes a `/healthz` endpoint returning 200 OK
**And** the operator watches for Beeper CRDs (Source, Investigation)

**Given** no external network access is required
**When** Beeper operates
**Then** all data remains on customer premises (FR41)

### Story 1.4: Source CRD & Prometheus Adapter

As an **Admin**,
I want to configure Prometheus as a metrics data source via CRD,
So that Beeper can query metrics for anomaly detection.

**Acceptance Criteria:**

**Given** the Source CRD is defined
**When** I apply a Source manifest:
```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  type: prometheus
  endpoint: http://prometheus:9090
  credentialsSecret: prometheus-creds
```
**Then** the operator reconciles and validates the configuration
**And** the Source status shows `connected: true` or error details

**Given** a valid Prometheus source is configured
**When** the operator queries Prometheus
**Then** it uses read-only credentials from K8s Secret (FR26)
**And** PromQL queries execute successfully

**Given** invalid credentials are provided
**When** the operator attempts connection
**Then** the Source status shows `connected: false`
**And** error details explain the failure

### Story 1.5: Loki Adapter

As an **Admin**,
I want to configure Loki as a log data source,
So that Beeper can query logs for investigation.

**Acceptance Criteria:**

**Given** the Source CRD supports Loki
**When** I apply a Loki Source manifest:
```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: loki-main
spec:
  type: loki
  endpoint: http://loki:3100
  credentialsSecret: loki-creds
```
**Then** the operator reconciles and validates the configuration
**And** the Source status shows connection state

**Given** a valid Loki source is configured
**When** the operator queries Loki
**Then** LogQL queries execute successfully
**And** log streams are accessible for investigation

### Story 1.6: Streaming Data Ingestion

As **Beeper**,
I want to receive pushed log and metric data via streaming connections,
So that I can detect anomalies in near-real-time without polling overhead.

**Acceptance Criteria:**

**Given** Prometheus is configured with remote_write to Beeper
**When** metrics are pushed
**Then** Beeper receives metrics via streaming connection (FR27)
**And** no additional latency is added to the monitored systems (FR30)

**Given** Loki is configured to push logs to Beeper
**When** log events are generated
**Then** Beeper receives log streams in real-time
**And** logs are buffered appropriately for processing

**Given** high volume data ingestion
**When** Beeper processes incoming streams
**Then** backpressure is handled gracefully
**And** the operator remains responsive

### Story 1.7: Source Status UI

As an **Admin**,
I want to view the status of all configured data sources,
So that I can verify Beeper is receiving data and troubleshoot issues.

**Acceptance Criteria:**

**Given** sources are configured
**When** I navigate to the Sources page in the UI
**Then** I see a list of all configured sources (FR28)
**And** each source shows: name, type, endpoint, connection status

**Given** a source has configuration errors
**When** I view the Sources page
**Then** the source shows amber/red status indicator
**And** error details are displayed (FR29)
**And** the error message is actionable (e.g., "Missing metric labels for service discovery")

**Given** the operator health endpoint exists
**When** I view the operator status
**Then** I see Beeper's operational health (FR40)
**And** component status (operator running, Qdrant connected)

### Story 1.8: LLM Provider Configuration

As an **Admin**,
I want to configure which LLM provider Beeper uses,
So that I can use my preferred AI provider and manage API keys.

**Acceptance Criteria:**

**Given** the Beeper ConfigMap/CRD supports LLM configuration
**When** I configure the LLM provider:
```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4
  apiKeySecret: anthropic-api-key
```
**Then** Beeper uses LiteLLM with the specified provider (FR42)
**And** API keys are read from K8s Secrets (NFR-S2)

**Given** the LLM configuration is invalid
**When** the operator validates configuration
**Then** clear error messages indicate the problem
**And** Beeper does not start investigations without valid LLM config

**Given** a valid LLM is configured
**When** I view operator status
**Then** LLM connectivity status is displayed

### Story 1.9: Investigation CRD & Pod Spawning

As **Beeper**,
I want to spawn Investigator pods for detected conditions,
So that each investigation runs in isolation with dedicated resources.

**Acceptance Criteria:**

**Given** the Investigation CRD is defined
**When** the operator detects a suspicious condition
**Then** it creates an Investigation custom resource
**And** the Investigation status tracks: `pending`, `running`, `completed`, `failed`

**Given** an Investigation CR is created
**When** the operator reconciles
**Then** a K8s Job is spawned with the investigator container (FR38)
**And** the Job has access to: Qdrant, LLM API, source credentials
**And** the Job is labeled with `investigation_id` for tracking

**Given** an investigator Job completes
**When** the operator reconciles
**Then** the Investigation CR status is updated
**And** the Job is cleaned up according to retention policy

**Given** an investigator Job fails
**When** the operator reconciles
**Then** the Investigation CR shows failure status with error details
**And** retry policy is applied if configured

---

## Epic 2: Knowledge Base

SRE team has a functional knowledge base wiki where they can import runbooks, search, view, edit, and track version history.

### Story 2.1: KB Wiki Interface

As an **SRE**,
I want to access a wiki-style interface for the Knowledge Base,
So that I can browse and read documentation in a human-friendly format.

**Acceptance Criteria:**

**Given** the UI is deployed
**When** I navigate to `/knowledge`
**Then** I see the KB wiki index page (FR36)
**And** I see a list of recent KB entries
**And** entries are organized by type (investigations, runbooks)

**Given** KB entries exist
**When** I click on an entry
**Then** I see the entry in human-readable wiki format (FR16)
**And** the entry displays: title, content, metadata (service, date, author)
**And** markdown content is rendered properly

**Given** an entry is linked to a service
**When** I view the entry
**Then** I see the service name as a clickable filter
**And** related entries for that service are suggested

### Story 2.2: Semantic Search

As an **SRE**,
I want to search the Knowledge Base using natural language queries,
So that I can find relevant information even without exact keywords.

**Acceptance Criteria:**

**Given** I am on the KB page
**When** I enter a natural language query like "database connection timeout errors"
**Then** semantically similar entries are returned (FR14)
**And** results are ranked by relevance
**And** search completes in sub-second time (NFR-P3)

**Given** search results are displayed
**When** I view the results
**Then** each result shows: title, snippet, relevance score, entry type
**And** the matching context is highlighted

**Given** no exact matches exist
**When** I search for a concept
**Then** semantically related entries are still surfaced
**And** "No exact matches, showing related entries" is indicated

### Story 2.3: Structured Search & Filtering

As an **SRE**,
I want to search the KB using structured filters,
So that I can narrow down results by service, error type, or date range.

**Acceptance Criteria:**

**Given** I am on the KB search page
**When** I apply filters:
- Service: `payments`
- Date range: Last 30 days
- Entry type: `investigation`
**Then** only matching entries are returned (FR15)
**And** filters can be combined with semantic search

**Given** filter options exist
**When** I view the filter panel
**Then** I see available filters: service, entry type, date range, severity
**And** filter values are populated from existing KB metadata

**Given** I apply a filter
**When** results are displayed
**Then** active filters are shown as removable chips
**And** I can clear all filters with one click

### Story 2.4: Runbook Import

As an **SRE Lead**,
I want to import existing runbooks into the Knowledge Base,
So that Beeper has seed context for investigations.

**Acceptance Criteria:**

**Given** I have runbook files (markdown, text, or common formats)
**When** I navigate to KB → Import
**Then** I can upload files or paste content (FR13)
**And** I can specify metadata: service, tags, entry type

**Given** I upload a markdown runbook
**When** the import processes
**Then** the runbook is parsed and stored in Qdrant
**And** embeddings are generated for semantic search
**And** the entry appears in the KB wiki

**Given** I import multiple runbooks
**When** import completes
**Then** I see a summary: X entries imported, Y warnings
**And** any parsing issues are reported with line numbers

**Given** a runbook has formatting issues
**When** import processes
**Then** best-effort parsing is applied
**And** warnings indicate what couldn't be parsed

### Story 2.5: KB Entry Editing

As an **SRE Lead**,
I want to directly edit Knowledge Base entries,
So that I can correct errors and add context.

**Acceptance Criteria:**

**Given** I am viewing a KB entry
**When** I click "Edit"
**Then** I see a markdown editor with the entry content (FR17)
**And** I can modify title, content, and metadata

**Given** I am editing an entry
**When** I save changes
**Then** the entry is updated in Qdrant
**And** embeddings are regenerated for the new content
**And** a new version is created (for history tracking)

**Given** I am editing
**When** I click "Preview"
**Then** I see the rendered markdown
**And** I can toggle between edit and preview modes

**Given** another user is viewing the entry
**When** I save changes
**Then** they see the updated content on refresh
**And** no data is lost

### Story 2.6: Version History

As an **SRE**,
I want to view the version history of any KB entry,
So that I can see how documentation evolved and who made changes.

**Acceptance Criteria:**

**Given** I am viewing a KB entry
**When** I click "History"
**Then** I see a list of all versions (FR21)
**And** each version shows: version number, date, author, change summary

**Given** version history is displayed
**When** I click on a previous version
**Then** I can view that version's content
**And** I see "Viewing version X of Y" indicator

**Given** I am viewing an old version
**When** I want to restore it
**Then** I can click "Restore this version"
**And** a new version is created with the old content

### Story 2.7: Version Diff View

As an **SRE**,
I want to compare versions of a KB entry,
So that I can see exactly what changed between versions.

**Acceptance Criteria:**

**Given** I am viewing version history
**When** I select two versions to compare
**Then** I see a side-by-side or unified diff view (FR22)
**And** additions are highlighted in green
**And** deletions are highlighted in red

**Given** I am viewing a diff
**When** the changes are extensive
**Then** I can toggle between "changes only" and "full context"
**And** I can navigate between change hunks

**Given** Beeper made corrections based on human feedback
**When** I view the diff
**Then** I can see exactly what Beeper learned
**And** the diff helps me verify the correction was applied correctly

---

## Epic 3: Investigation Engine

Beeper can detect anomalies in logs/metrics, spawn investigators, correlate signals across layers, generate root cause hypotheses, and document findings to the KB.

### Story 3.1: Anomaly Detection Engine

As **Beeper**,
I want to continuously monitor incoming log and metric streams for anomalous patterns,
So that suspicious conditions are identified for investigation.

**Acceptance Criteria:**

**Given** data sources are configured and streaming
**When** the operator processes incoming data
**Then** anomaly detection runs continuously (FR1)
**And** detection latency is in seconds from occurrence (NFR-P1)

**Given** metrics show unusual patterns (spike, drop, deviation)
**When** the anomaly detector evaluates
**Then** a suspicious condition is flagged
**And** the condition includes: source, metric/log pattern, timestamp, severity estimate

**Given** logs contain error patterns or unusual frequencies
**When** the anomaly detector evaluates
**Then** log-based anomalies are detected
**And** relevant log lines are captured as context

**Given** normal operational patterns
**When** the detector evaluates
**Then** no false positives are generated for expected behavior
**And** baseline learning adapts to environment patterns

### Story 3.2: Investigator Agent Scaffold

As **Beeper**,
I want a Python investigator agent that can be spawned for each suspicious condition,
So that investigations run in isolation with dedicated resources.

**Acceptance Criteria:**

**Given** the operator creates an Investigation CR
**When** the investigator Job starts
**Then** the Python agent initializes with:
- Investigation ID and condition details
- Qdrant connection for KB access
- LLM client (LiteLLM) configuration
- Source credentials for querying Prometheus/Loki

**Given** the investigator agent starts
**When** it begins processing
**Then** it logs structured JSON with `investigation_id` context
**And** progress updates are written to Investigation CR status

**Given** the investigation completes or fails
**When** the agent exits
**Then** exit code reflects success/failure
**And** final status is persisted before termination

### Story 3.3: Customer Impact Assessment

As an **Investigator**,
I want to assess whether a detected condition has customer impact,
So that I can prioritize appropriately and focus on real issues.

**Acceptance Criteria:**

**Given** a suspicious condition is detected
**When** the investigator starts
**Then** it first assesses customer impact (FR3)
**And** uses lightweight LLM model for initial screening (FR43)

**Given** the condition affects customer-facing services
**When** impact assessment completes
**Then** the investigation is flagged as `customer_impacting: true`
**And** investigation proceeds with higher priority

**Given** the condition is internal/infrastructure only
**When** impact assessment completes
**Then** the investigation is flagged as `customer_impacting: false`
**And** investigation still proceeds but with appropriate priority

**Given** impact cannot be determined
**When** assessment is uncertain
**Then** `customer_impacting: unknown` is set
**And** investigation proceeds with default priority

### Story 3.4: KB Query & Prior Research

As an **Investigator**,
I want to query the Knowledge Base for similar past incidents,
So that I can build on prior research and avoid re-investigating known issues.

**Acceptance Criteria:**

**Given** an investigation is in progress
**When** the investigator queries the KB
**Then** semantically similar past investigations are retrieved (FR5)
**And** results include: investigation ID, root cause, resolution, confidence

**Given** similar incidents exist in the KB
**When** the investigator analyzes them
**Then** it builds on prior research rather than starting fresh (FR6)
**And** references to prior investigations are included in findings

**Given** an exact match is found (same root cause signature)
**When** the investigator identifies the match
**Then** confidence level is elevated
**And** prior resolution is recommended with high confidence

**Given** the KB is temporarily unavailable
**When** the investigator attempts to query
**Then** the investigation continues without KB context (NFR-R2)
**And** findings are buffered locally for later KB write

### Story 3.5: Cross-Layer Signal Correlation

As an **Investigator**,
I want to correlate signals across multiple architectural layers,
So that I can identify root causes that span infrastructure, platform, application, and data layers.

**Acceptance Criteria:**

**Given** an investigation is analyzing a condition
**When** the investigator gathers signals
**Then** it queries across architectural layers (FR4):
- Infrastructure (K8s nodes, resources)
- Platform (K8s services, deployments)
- Application (service logs, error rates)
- Data (database metrics, query patterns)

**Given** correlated signals are found
**When** the investigator analyzes them
**Then** temporal correlation is established (what happened when)
**And** causal chains are hypothesized (A caused B caused C)

**Given** signals span multiple services
**When** correlation completes
**Then** the service dependency chain is documented
**And** the originating layer is identified

**Given** signals are ambiguous
**When** correlation is uncertain
**Then** multiple hypotheses are generated
**And** each hypothesis includes confidence level

### Story 3.6: RCA Hypothesis Generation

As an **Investigator**,
I want to generate a root cause hypothesis with an explicit confidence level,
So that SREs understand the certainty of my findings.

**Acceptance Criteria:**

**Given** signal correlation is complete
**When** the investigator synthesizes findings
**Then** a root cause hypothesis is generated (FR7)
**And** the hypothesis includes:
- Root cause description
- Confidence level (high/medium/low with percentage)
- Supporting evidence (correlated signals)
- Alternative hypotheses if confidence < high

**Given** strong signal correlation exists
**When** generating hypothesis
**Then** powerful LLM model is used for deep RCA (FR44)
**And** confidence reflects strength of evidence

**Given** weak or conflicting signals
**When** generating hypothesis
**Then** confidence is appropriately low
**And** the hypothesis explicitly states uncertainty
**And** additional data needs are identified

**Given** a known issue pattern from KB
**When** generating hypothesis
**Then** the KB match boosts confidence
**And** the prior incident is cited as supporting evidence

### Story 3.7: Resolution Recommendations

As an **Investigator**,
I want to recommend resolution actions based on investigation findings,
So that SREs have actionable next steps.

**Acceptance Criteria:**

**Given** a root cause hypothesis is generated
**When** the investigator generates recommendations
**Then** resolution actions are suggested (FR8)
**And** each recommendation includes:
- Action description
- Confidence level
- Expected outcome
- Risk assessment

**Given** a similar past incident was resolved
**When** generating recommendations
**Then** the prior resolution is recommended
**And** confidence is elevated based on past success

**Given** the root cause is uncertain
**When** generating recommendations
**Then** safe diagnostic actions are recommended first
**And** "gather more information" steps are included

**Given** multiple resolution paths exist
**When** generating recommendations
**Then** options are ranked by confidence and risk
**And** trade-offs are explained

### Story 3.8: Investigation Documentation

As an **Investigator**,
I want to document my investigation process and findings to the Knowledge Base,
So that the investigation is preserved for future reference and learning.

**Acceptance Criteria:**

**Given** an investigation completes
**When** the investigator documents findings
**Then** a KB entry is created with (FR9):
- Investigation summary
- Detected condition
- Correlated signals
- Root cause hypothesis
- Recommended resolution
- Confidence levels throughout

**Given** the KB is available
**When** documentation is written
**Then** the entry is stored in the `knowledge` collection
**And** embeddings are generated for semantic search
**And** metadata includes: service, timestamp, investigation_id

**Given** the KB is temporarily unavailable
**When** documentation is attempted
**Then** findings are buffered locally (NFR-R2)
**And** retry logic persists until KB accepts the write

**Given** the investigation builds on prior research
**When** documenting
**Then** links to referenced prior investigations are included
**And** the knowledge graph grows richer

### Story 3.9: Tiered LLM Model Selection

As **Beeper**,
I want to use lightweight models for screening and powerful models for deep RCA,
So that I balance cost and capability appropriately.

**Acceptance Criteria:**

**Given** LLM configuration includes tiered models
**When** the investigator needs LLM assistance
**Then** model selection is based on task type:
- Screening/triage: `claude-3-haiku` (FR43)
- Investigation/correlation: `claude-sonnet-4` (FR44)
- Deep RCA/complex reasoning: `claude-opus-4` (FR44)

**Given** initial screening is performed
**When** using lightweight model
**Then** response latency is fast
**And** cost per screening is minimal

**Given** deep RCA is required
**When** escalating to powerful model
**Then** the escalation is logged with rationale
**And** the more capable model is used for reasoning

**Given** model routing decisions are made
**When** the investigation completes
**Then** model usage is tracked for cost reporting

### Story 3.10: LLM Response Caching

As **Beeper**,
I want to cache and memoize LLM results to avoid redundant calls,
So that I reduce costs and improve response times for recurring patterns.

**Acceptance Criteria:**

**Given** an LLM query is made
**When** a similar query was recently made
**Then** the cached response is returned (FR45)
**And** cache hit is logged for metrics

**Given** an investigation encounters a recurring issue
**When** querying for analysis
**Then** prior LLM reasoning is retrieved from cache
**And** only delta analysis requires new LLM calls

**Given** cache entries exist
**When** the underlying data changes significantly
**Then** cache is invalidated appropriately
**And** stale reasoning is not returned

**Given** caching is operational
**When** reviewing costs
**Then** cache hit rate is reported
**And** estimated cost savings are visible

---

## Epic 4: Investigation Experience

SREs can observe Beeper's investigations in real-time, view recommendations with confidence levels, confirm/reject resolutions, and mark investigations complete.

### Story 4.1: Investigation List View

As an **SRE**,
I want to view a list of active investigations,
So that I can see what Beeper is currently working on and prioritize my attention.

**Acceptance Criteria:**

**Given** I navigate to the Investigations page
**When** the page loads
**Then** I see a list of all active investigations (FR31)
**And** each investigation shows: ID, status, service, started time, severity

**Given** investigations are in various states
**When** I view the list
**Then** investigations are grouped/sorted by status:
- `investigating` (in progress)
- `awaiting_confirmation` (needs human input)
- `completed` (recently finished)

**Given** new investigations start
**When** I am viewing the list
**Then** the list updates via SSE without page refresh
**And** new investigations appear at the top

**Given** I want to filter investigations
**When** I use filter controls
**Then** I can filter by: status, service, severity, date range

### Story 4.2: Real-Time Investigation Pane

As an **SRE**,
I want to view the real-time reasoning of any active Investigator,
So that I can observe Beeper's investigation process as it happens.

**Acceptance Criteria:**

**Given** I click on an active investigation
**When** the investigation pane opens
**Then** I see Beeper's reasoning process in real-time (FR32, FR10)
**And** updates stream via SSE (NFR-P2)

**Given** the investigator is working
**When** I observe the pane
**Then** I see the current step: "Assessing impact", "Querying KB", "Correlating signals", etc.
**And** I see evidence being gathered in real-time
**And** I see the reasoning chain as it develops

**Given** the investigation progresses
**When** new findings emerge
**Then** they appear in the pane without refresh
**And** timestamps show when each finding was made

**Given** the investigation pane is open
**When** I want to see raw data
**Then** I can expand sections to see:
- Raw log snippets
- Metric values
- KB matches found

### Story 4.3: Recommendations & Confidence Display

As an **SRE**,
I want to view recommended resolutions with confidence levels,
So that I understand how certain Beeper is about its findings.

**Acceptance Criteria:**

**Given** an investigation has generated recommendations
**When** I view the investigation
**Then** I see recommendations with confidence levels (FR33)
**And** confidence is displayed as: High (>80%), Medium (50-80%), Low (<50%)

**Given** recommendations are displayed
**When** I view them
**Then** each recommendation shows:
- Action to take
- Confidence level with visual indicator
- Supporting evidence summary
- Risk assessment

**Given** multiple recommendations exist
**When** I view the list
**Then** they are ranked by confidence
**And** the top recommendation is highlighted

**Given** confidence is low
**When** I view recommendations
**Then** a warning indicates uncertainty
**And** alternative hypotheses are shown
**And** "Gather more information" options are suggested

### Story 4.4: KB Entry Navigation

As an **SRE**,
I want to navigate from an investigation to related Knowledge Base entries,
So that I can see prior context and historical information.

**Acceptance Criteria:**

**Given** an investigation references KB entries
**When** I view the investigation
**Then** related KB entries are linked (FR34)
**And** I can click to open the KB entry

**Given** similar past incidents exist
**When** Beeper found them during investigation
**Then** they appear in a "Related Incidents" section
**And** each shows: title, date, root cause summary, similarity score

**Given** I click a related KB entry
**When** the entry opens
**Then** I can view it in a side panel or new tab
**And** I can easily return to the investigation

**Given** the investigation builds on prior research
**When** I view the investigation
**Then** I see "Building on investigation KB-XXX" with link
**And** the connection between old and new is clear

### Story 4.5: Resolution Confirmation

As an **SRE**,
I want to confirm or reject an Investigator's resolution recommendation,
So that I maintain control over actions taken.

**Acceptance Criteria:**

**Given** an investigation has a recommendation awaiting confirmation
**When** I view the investigation
**Then** I see "Confirm" and "Reject" buttons (FR11)
**And** the recommendation details are clearly displayed

**Given** I click "Confirm"
**When** confirming a resolution
**Then** I can optionally add a comment
**And** the confirmation is recorded
**And** the investigation status updates to reflect confirmation

**Given** I click "Reject"
**When** rejecting a resolution
**Then** I must provide a reason (dropdown + free text)
**And** the rejection is recorded
**And** the investigation may continue with alternative approaches

**Given** I reject with correction
**When** I provide the correct resolution
**Then** my correction is captured for Beeper learning
**And** the investigation can be resolved with my correction

### Story 4.6: Investigation Resolution

As an **SRE**,
I want to mark an investigation as resolved with outcome confirmation,
So that the investigation is properly closed and documented.

**Acceptance Criteria:**

**Given** an investigation is ready to close
**When** I click "Resolve Investigation"
**Then** I see a resolution form (FR12)
**And** I can select outcome: "Resolved", "Not an issue", "Escalated", "Unresolved"

**Given** I select "Resolved"
**When** completing resolution
**Then** I confirm the resolution action taken
**And** I can rate Beeper's accuracy: "Correct", "Partially correct", "Incorrect"
**And** the KB entry is updated with resolution confirmation

**Given** I select "Not an issue"
**When** completing resolution
**Then** I indicate why (false positive, expected behavior, etc.)
**And** this feedback helps improve anomaly detection

**Given** I select "Escalated"
**When** completing resolution
**Then** I indicate escalation target
**And** the investigation is marked but not closed

**Given** resolution is complete
**When** the investigation closes
**Then** final documentation is written to KB
**And** the investigation appears in "Completed" list
**And** MTTR is calculated for this investigation

---

## Epic 5: Living Knowledge

KB becomes a self-improving system where SREs can provide conversational corrections, Beeper learns from feedback, and trust enables direct publishing.

### Story 5.1: Conversational Corrections Interface

As an **SRE Lead**,
I want to provide conversational corrections to Beeper,
So that I can correct entries naturally without manual editing.

**Acceptance Criteria:**

**Given** I am viewing a KB entry
**When** I click "Suggest Correction" or open the correction panel
**Then** I see a chat-style interface for providing feedback (FR18)
**And** I can type natural language corrections like:
- "The root cause wasn't the load balancer - it was a deployment that changed the health check timeout"
- "Add that this only happens during peak traffic hours"
- "Remove the section about database - that was a red herring"

**Given** I submit a conversational correction
**When** the correction is processed
**Then** I see "Processing correction..." status
**And** Beeper acknowledges the correction with a summary of understood changes

**Given** Beeper misunderstands my correction
**When** I see the proposed changes
**Then** I can clarify or rephrase my correction
**And** the conversation continues until the correction is right

**Given** corrections are submitted
**When** I view my correction history
**Then** I see past corrections I've made
**And** I can see which were applied and their impact

### Story 5.2: Beeper Revision Processing

As **Beeper**,
I want to revise Knowledge Base entries based on conversational corrections,
So that the KB reflects accurate, human-validated information.

**Acceptance Criteria:**

**Given** an SRE submits a conversational correction
**When** Beeper processes it
**Then** Beeper understands the intent and generates a revision (FR19)
**And** the revision is shown to the SRE for approval before applying

**Given** Beeper generates a revision
**When** the SRE reviews it
**Then** the SRE sees:
- Original content
- Proposed revision
- Diff highlighting changes
- "Apply" or "Revise further" options

**Given** the SRE approves the revision
**When** applying the change
**Then** the KB entry is updated
**And** a new version is created with attribution
**And** the correction is logged for learning

**Given** the revision needs adjustment
**When** the SRE provides additional feedback
**Then** Beeper refines the revision
**And** the cycle continues until approved

### Story 5.3: Learning from Diffs

As **Beeper**,
I want to learn from the diff between my documentation and human corrections,
So that I improve my future investigations and documentation.

**Acceptance Criteria:**

**Given** a human correction is applied
**When** the diff is recorded
**Then** Beeper analyzes the pattern of correction (FR20)
**And** learns categories like:
- Missing context I should have included
- Incorrect correlations I made
- Wrong conclusions from evidence
- Unnecessary information I added

**Given** multiple corrections follow a pattern
**When** Beeper detects the pattern
**Then** investigation prompts are adjusted to address the gap
**And** future investigations incorporate the learning

**Given** a correction is for a specific service
**When** learning is applied
**Then** service-specific context is weighted in future investigations
**And** the learning is scoped appropriately (not over-generalized)

**Given** learning is accumulated
**When** reviewing Beeper's improvement
**Then** SRE Leads can see:
- Correction categories and frequencies
- Areas where Beeper has improved
- Remaining gaps in understanding

### Story 5.4: Graduated Authoring Trust

As **Beeper**,
I want to publish entries directly as trust is established,
So that validated accurate documentation flows faster while maintaining quality.

**Acceptance Criteria:**

**Given** Beeper creates a new KB entry
**When** trust level is "new" (default)
**Then** the entry is marked "Draft - Awaiting Review" (FR23)
**And** SRE must approve before it becomes active

**Given** Beeper's entries for a service have high accuracy
**When** trust metrics meet threshold (e.g., >90% accuracy over 10+ entries)
**Then** trust level graduates to "trusted" for that service
**And** future entries are published directly (still versioned)

**Given** trust level is "trusted"
**When** Beeper publishes directly
**Then** the entry is immediately visible
**And** it's flagged as "Auto-published" for transparency
**And** SREs can still review and correct

**Given** a directly published entry is corrected
**When** the correction is significant
**Then** trust level may be re-evaluated
**And** trust can be downgraded if accuracy drops

**Given** trust levels exist
**When** an SRE Lead views trust settings
**Then** they see:
- Per-service trust levels
- Accuracy metrics backing the trust level
- Option to manually adjust trust

---

## Epic 6: Operations & Insights

Admins can control LLM costs with spending caps, see which environments drive excessive costs, and team leads can view MTTR trends.

### Story 6.1: MTTR Trends Dashboard

As an **SRE Lead**,
I want to view MTTR trends over time,
So that I can measure Beeper's impact and report on reliability improvements.

**Acceptance Criteria:**

**Given** investigations have been resolved
**When** I navigate to the Metrics/Insights page
**Then** I see MTTR (Mean Time To Resolution) trends (FR35)
**And** the chart shows MTTR over configurable time periods (week, month, quarter)

**Given** MTTR data is displayed
**When** I view the dashboard
**Then** I see:
- Overall MTTR trend line
- MTTR by service breakdown
- MTTR by severity level
- Comparison to baseline (pre-Beeper if available)

**Given** I want to drill down
**When** I click on a data point
**Then** I see the investigations that contributed to that MTTR
**And** I can navigate to individual investigations

**Given** MTTR is improving
**When** viewing the dashboard
**Then** improvement percentage is highlighted
**And** I can export data for leadership reports

**Given** specific services have different MTTR
**When** I filter by service
**Then** I see service-specific MTTR trends
**And** I can identify services that need attention

### Story 6.2: LLM Spending Caps

As an **Admin**,
I want to set spending caps and rate limits for LLM usage,
So that I can control costs and prevent runaway spending.

**Acceptance Criteria:**

**Given** I access the Admin settings
**When** I configure LLM spending controls
**Then** I can set (FR46):
- Daily spending cap (e.g., $50/day)
- Monthly spending cap (e.g., $500/month)
- Rate limit (e.g., max 100 investigations/hour)

**Given** spending caps are configured
**When** the cap is approached (80% threshold)
**Then** a warning is logged
**And** the Admin is notified (via configured channel or UI alert)

**Given** spending cap is reached
**When** a new investigation would exceed the cap
**Then** investigation is queued or deprioritized
**And** only critical/high-severity investigations proceed
**And** clear messaging indicates cap enforcement

**Given** rate limits are configured
**When** investigation rate exceeds limit
**Then** new investigations are throttled
**And** backpressure is applied gracefully

**Given** caps are enforced
**When** I view the Admin dashboard
**Then** I see:
- Current spend vs. cap (progress bar)
- Projected spend for period
- Rate of consumption

### Story 6.3: Cost Visibility & Alerts

As an **Admin**,
I want to see which environments or services drive excessive investigation costs,
So that I can identify noisy systems and optimize Beeper's focus.

**Acceptance Criteria:**

**Given** investigations have run with LLM costs
**When** I view the Cost Insights page
**Then** I see cost breakdown by (FR47):
- Service/namespace
- Investigation type
- Time period
- LLM model tier used

**Given** a service generates excessive costs
**When** viewing the dashboard
**Then** that service is flagged as "High Cost"
**And** I see:
- Total cost for service
- Investigation count
- Cost per investigation
- Trend (increasing/stable/decreasing)

**Given** excessive cost is detected
**When** thresholds are exceeded
**Then** an alert surfaces in the UI
**And** recommendation is provided:
- "payments service generated $45 in LLM costs (3x average) - consider tuning anomaly thresholds"

**Given** I identify a noisy environment
**When** I want to take action
**Then** I can:
- Adjust anomaly detection sensitivity for that service
- Exclude certain log patterns from investigation
- Set service-specific rate limits

**Given** cost data exists
**When** I want to report
**Then** I can export cost reports (CSV, JSON)
**And** data includes model usage breakdown
