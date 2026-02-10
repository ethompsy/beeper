# Story 1.1: Project Scaffolding

Status: done

## Story

As an **Admin/Developer**,
I want the Beeper project structure and CI pipeline established,
So that I have a foundation for building all components.

## Acceptance Criteria

### AC1: Monorepo Structure
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

### AC2: CI Pipeline
**Given** the CI pipeline is configured
**When** I push to main branch
**Then** GitHub Actions runs lint and test jobs for all components
**And** Docker images can be built for each component

### AC3: OpenAPI Specification
**Given** the OpenAPI specification exists
**When** I view `openapi/beeper-api.yaml`
**Then** I see the API structure with placeholder endpoints for:
- `/api/v1/investigations`
- `/api/v1/knowledge`
- `/api/v1/sources`
**And** the spec follows OpenAPI 3.1 with RFC 7807 error schemas

## Tasks / Subtasks

- [x] Task 1: Create monorepo structure (AC: #1)
  - [x] 1.1: Create root directory with README.md, LICENSE (Apache 2.0), CONTRIBUTING.md, .gitignore
  - [x] 1.2: Create `operator/` directory with Cargo.toml scaffold
  - [x] 1.3: Create `investigator/` directory with pyproject.toml (poetry)
  - [x] 1.4: Create `ui/` directory with pyproject.toml (poetry)
  - [x] 1.5: Create `openapi/` directory structure
  - [x] 1.6: Create `helm/beeper/` chart scaffold
  - [x] 1.7: Create `scripts/` directory with setup-dev.sh placeholder
  - [x] 1.8: Create docker-compose.yaml for local dev

- [x] Task 2: Initialize Rust operator component (AC: #1)
  - [x] 2.1: Run `cargo init` in operator/ directory
  - [x] 2.2: Add dependencies to Cargo.toml: kube, kube-runtime, tokio, serde, serde_json, tracing
  - [x] 2.3: Create src/main.rs with minimal "Hello, Beeper Operator" entry point
  - [x] 2.4: Create src/lib.rs exporting modules
  - [x] 2.5: Verify `cargo build` succeeds
  - [x] 2.6: Verify `cargo test` runs (even if no tests yet)

- [x] Task 3: Initialize Python investigator component (AC: #1)
  - [x] 3.1: Run `poetry init` in investigator/ directory
  - [x] 3.2: Add dependencies: anthropic, httpx, pydantic, qdrant-client, litellm
  - [x] 3.3: Add dev dependencies: pytest, ruff, mypy
  - [x] 3.4: Create beeper_investigator/__init__.py
  - [x] 3.5: Create beeper_investigator/main.py with minimal entry point
  - [x] 3.6: Verify `poetry install` succeeds
  - [x] 3.7: Verify `poetry run pytest` runs

- [x] Task 4: Initialize Python UI component (AC: #1)
  - [x] 4.1: Run `poetry init` in ui/ directory
  - [x] 4.2: Add dependencies: flask, qdrant-client
  - [x] 4.3: Add dev dependencies: pytest, ruff, mypy
  - [x] 4.4: Create beeper_ui/__init__.py
  - [x] 4.5: Create beeper_ui/app.py with minimal Flask app
  - [x] 4.6: Download htmx.min.js to static/js/
  - [x] 4.7: Create templates/base.html with HTMX included
  - [x] 4.8: Verify `poetry run flask run` starts server

- [x] Task 5: Create OpenAPI specification scaffold (AC: #3)
  - [x] 5.1: Create openapi/beeper-api.yaml with OpenAPI 3.1 header
  - [x] 5.2: Add info section with title, version, description
  - [x] 5.3: Add placeholder paths for /api/v1/investigations
  - [x] 5.4: Add placeholder paths for /api/v1/knowledge
  - [x] 5.5: Add placeholder paths for /api/v1/sources
  - [x] 5.6: Add RFC 7807 error schema in components/schemas
  - [x] 5.7: Create openapi/schemas/ directory with investigation.yaml, knowledge.yaml, source.yaml placeholders

- [x] Task 6: Create Helm chart scaffold (AC: #1)
  - [x] 6.1: Create helm/beeper/Chart.yaml
  - [x] 6.2: Create helm/beeper/values.yaml with default configuration
  - [x] 6.3: Create helm/beeper/values-dev.yaml for development overrides
  - [x] 6.4: Create helm/beeper/templates/_helpers.tpl
  - [x] 6.5: Create placeholder templates: operator-deployment.yaml, ui-deployment.yaml
  - [x] 6.6: Create helm/beeper/README.md

- [x] Task 7: Create CI pipeline (AC: #2)
  - [x] 7.1: Create .github/workflows/ci.yml
  - [x] 7.2: Add Rust job: cargo fmt --check, cargo clippy, cargo test
  - [x] 7.3: Add Python investigator job: poetry install, ruff check, pytest
  - [x] 7.4: Add Python UI job: poetry install, ruff check, pytest
  - [x] 7.5: Add Helm lint job: helm lint ./helm/beeper
  - [x] 7.6: Create .github/workflows/release.yml placeholder
  - [x] 7.7: Create .github/CODEOWNERS file

- [x] Task 8: Create Docker configurations (AC: #1, #2)
  - [x] 8.1: Create operator/Dockerfile (multi-stage Rust build)
  - [x] 8.2: Create investigator/Dockerfile (Python with poetry)
  - [x] 8.3: Create ui/Dockerfile (Python/Flask with poetry)
  - [x] 8.4: Create docker-compose.yaml with all services + Qdrant

- [x] Task 9: Create development scripts (AC: #1)
  - [x] 9.1: Create scripts/setup-dev.sh for local environment setup
  - [x] 9.2: Create scripts/generate-clients.sh placeholder for OpenAPI client generation

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Project Structure & Boundaries]

This story establishes the foundation that ALL future stories depend on. The structure MUST match the architecture exactly:

```
beeper/
├── README.md
├── LICENSE                          # Apache 2.0 (open source)
├── CONTRIBUTING.md
├── .gitignore
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   # Build + test all components
│   │   ├── release.yml              # Build + push containers (placeholder)
│   │   └── helm-lint.yml            # Validate Helm chart
│   └── CODEOWNERS
├── openapi/                         # Shared API specifications
│   ├── beeper-api.yaml              # Main OpenAPI spec
│   └── schemas/
│       ├── investigation.yaml
│       ├── knowledge.yaml
│       └── source.yaml
├── operator/                        # Rust K8s operator
│   ├── Cargo.toml
│   ├── Dockerfile
│   └── src/
│       ├── main.rs
│       └── lib.rs
├── investigator/                    # Python investigator agent
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── beeper_investigator/
│       ├── __init__.py
│       └── main.py
├── ui/                              # Flask web UI
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── beeper_ui/
│       ├── __init__.py
│       ├── app.py
│       ├── templates/
│       │   └── base.html
│       └── static/
│           └── js/
│               └── htmx.min.js
├── helm/
│   └── beeper/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-dev.yaml
│       ├── templates/
│       │   └── _helpers.tpl
│       └── README.md
├── scripts/
│   ├── setup-dev.sh
│   └── generate-clients.sh
└── docker-compose.yaml
```

### Technology Stack Requirements

**Source:** [architecture.md - Technology Stack Decisions]

| Component | Technology | Version |
|-----------|------------|---------|
| K8s Controller | Rust + kube-rs | Rust stable, kube latest |
| Investigator | Python | 3.11+ |
| UI | Flask + HTMX | Flask 3.x, HTMX 1.9+ |
| Package Manager (Rust) | Cargo | Latest |
| Package Manager (Python) | Poetry | 1.7+ |
| CI/CD | GitHub Actions | N/A |

### Rust Operator Dependencies (Cargo.toml)

```toml
[package]
name = "beeper-operator"
version = "0.1.0"
edition = "2021"

[dependencies]
kube = { version = "0.87", features = ["runtime", "derive"] }
kube-runtime = "0.87"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

[dev-dependencies]
tokio-test = "0.4"
```

### Python Investigator Dependencies (pyproject.toml)

```toml
[tool.poetry]
name = "beeper-investigator"
version = "0.1.0"
description = "Beeper investigation agent"
authors = ["Beeper Team"]

[tool.poetry.dependencies]
python = "^3.11"
anthropic = "^0.18"
httpx = "^0.27"
pydantic = "^2.6"
qdrant-client = "^1.8"
litellm = "^1.30"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
ruff = "^0.3"
mypy = "^1.8"
```

### Python UI Dependencies (pyproject.toml)

```toml
[tool.poetry]
name = "beeper-ui"
version = "0.1.0"
description = "Beeper web UI"
authors = ["Beeper Team"]

[tool.poetry.dependencies]
python = "^3.11"
flask = "^3.0"
qdrant-client = "^1.8"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
ruff = "^0.3"
mypy = "^1.8"
```

### OpenAPI 3.1 Structure

**Source:** [architecture.md - API & Communication Patterns]

The OpenAPI spec MUST follow these patterns:
- Base path: `/api/v1/`
- Resources: Plural nouns
- Error format: RFC 7807 Problem Details

```yaml
openapi: '3.1.0'
info:
  title: Beeper API
  version: 0.1.0
  description: Agentic SRE platform API

paths:
  /api/v1/investigations:
    get:
      summary: List investigations
      responses:
        '200':
          description: List of investigations
  /api/v1/knowledge:
    get:
      summary: Search knowledge base
  /api/v1/sources:
    get:
      summary: List configured sources

components:
  schemas:
    Problem:
      type: object
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
```

### GitHub Actions CI Structure

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  rust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo fmt --check
        working-directory: operator
      - run: cargo clippy -- -D warnings
        working-directory: operator
      - run: cargo test
        working-directory: operator

  python-investigator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install poetry
      - run: poetry install
        working-directory: investigator
      - run: poetry run ruff check .
        working-directory: investigator
      - run: poetry run pytest
        working-directory: investigator

  python-ui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install poetry
      - run: poetry install
        working-directory: ui
      - run: poetry run ruff check .
        working-directory: ui
      - run: poetry run pytest
        working-directory: ui

  helm:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - run: helm lint ./helm/beeper
```

### Docker Compose for Local Dev

```yaml
# docker-compose.yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  # Prometheus and Loki for local testing (optional)
  # prometheus:
  #   image: prom/prometheus:latest
  #   ports:
  #     - "9090:9090"

  # loki:
  #   image: grafana/loki:latest
  #   ports:
  #     - "3100:3100"

volumes:
  qdrant_data:
```

### Testing Requirements

- **Rust:** `cargo test` must pass (even with no tests initially)
- **Python:** `pytest` must pass (even with no tests initially)
- **Linting:** All linters must pass in CI
- **Helm:** `helm lint` must pass

### Project Structure Notes

- **Naming Convention:** All directories use lowercase with hyphens for multi-word names
- **Python Packages:** Use underscores for package names (beeper_investigator, beeper_ui)
- **Tests:** Place in `tests/` directory within each component
- **Documentation:** Each component should have its own README.md

### References

- [Source: architecture.md#Project Structure & Boundaries]
- [Source: architecture.md#Technology Stack Decisions]
- [Source: architecture.md#Implementation Patterns & Consistency Rules]
- [Source: architecture.md#Initialization Approach]
- [Source: epics.md#Story 1.1: Project Scaffolding]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Updated Rust to 1.93.0 to support latest kube-rs dependencies
- Added k8s-openapi with v1_30 feature for Kubernetes API compatibility
- Updated kube-rs from 0.87 to 0.95 for Rust compatibility

### Completion Notes List

- ✅ Created complete monorepo structure matching architecture specification
- ✅ Initialized Rust operator with kube-rs 0.95, cargo build and cargo test pass
- ✅ Initialized Python investigator with poetry, pytest passes (2 tests)
- ✅ Initialized Python UI with Flask + HTMX, pytest passes (3 tests)
- ✅ Created OpenAPI 3.1 specification with RFC 7807 error schemas
- ✅ Created Helm chart scaffold with operator and UI deployments
- ✅ Created GitHub Actions CI pipeline for all components
- ✅ Created multi-stage Dockerfiles for all components
- ✅ Created development scripts (setup-dev.sh, generate-clients.sh)
- ✅ All linting passes: cargo fmt, cargo clippy, ruff check, helm lint

### File List

**New Files:**
- README.md
- LICENSE
- CONTRIBUTING.md
- VISION.md
- .gitignore
- docker-compose.yaml
- operator/Cargo.lock
- investigator/poetry.lock
- ui/poetry.lock
- operator/Cargo.toml
- operator/Dockerfile
- operator/src/main.rs
- operator/src/lib.rs
- investigator/pyproject.toml
- investigator/Dockerfile
- investigator/README.md
- investigator/beeper_investigator/__init__.py
- investigator/beeper_investigator/main.py
- investigator/tests/__init__.py
- investigator/tests/test_main.py
- ui/pyproject.toml
- ui/Dockerfile
- ui/README.md
- ui/beeper_ui/__init__.py
- ui/beeper_ui/app.py
- ui/beeper_ui/templates/base.html
- ui/beeper_ui/static/js/htmx.min.js
- ui/tests/__init__.py
- ui/tests/test_app.py
- openapi/beeper-api.yaml
- openapi/schemas/investigation.yaml
- openapi/schemas/knowledge.yaml
- openapi/schemas/source.yaml
- helm/beeper/Chart.yaml
- helm/beeper/values.yaml
- helm/beeper/values-dev.yaml
- helm/beeper/README.md
- helm/beeper/templates/_helpers.tpl
- helm/beeper/templates/operator-deployment.yaml
- helm/beeper/templates/ui-deployment.yaml
- scripts/setup-dev.sh
- scripts/generate-clients.sh
- .github/workflows/ci.yml
- .github/workflows/release.yml
- .github/CODEOWNERS

## Change Log

- 2026-02-03: Story implementation completed - all 9 tasks with 40+ subtasks finished
- 2026-02-03: Code review fixes applied:
  - Fixed operator/Dockerfile Rust version (1.75 → 1.85)
  - Fixed deprecated Poetry --no-dev flag → --only main in Dockerfiles
  - Generated lock files (Cargo.lock, poetry.lock) for reproducible builds
  - Fixed type hints in ui/tests/test_app.py
  - Fixed README.md investigator run command
  - Added VISION.md and lock files to File List
