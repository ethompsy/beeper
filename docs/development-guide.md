# Beeper Development Guide

This guide covers everything you need to get started developing on the Beeper platform, including environment setup, running each component locally, testing, linting, and contributing guidelines.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Repository Structure](#repository-structure)
- [Local Development Setup](#local-development-setup)
- [Running Components](#running-components)
  - [Operator (Rust)](#operator-rust)
  - [Investigator (Python)](#investigator-python)
  - [UI (Flask)](#ui-flask)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Linting and Formatting](#linting-and-formatting)
- [Type Checking](#type-checking)
- [Building Docker Images](#building-docker-images)
- [CI/CD](#cicd)
- [Code Conventions](#code-conventions)
- [Useful Scripts](#useful-scripts)
- [Contributing](#contributing)

---

## Prerequisites

Ensure the following tools are installed before proceeding:

| Tool | Version | Purpose |
|------|---------|---------|
| Rust (stable) | Latest stable | Operator service |
| Python | 3.11+ | Investigator and UI services |
| Poetry | 1.7+ | Python dependency management |
| Docker | Latest | Container runtime |
| Docker Compose | Latest | Local stack orchestration |
| Kubernetes | Any supported | Production deployment |
| Helm | 3.x | Kubernetes chart deployment |

Install Rust via [rustup](https://rustup.rs/):

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Install Poetry via the [official installer](https://python-poetry.org/docs/#installation):

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

---

## Repository Structure

Beeper is a monorepo containing three application components and a Helm chart:

```
beeper/
├── operator/          # Rust-based Kubernetes operator and ingestion service
├── investigator/      # Python AI investigation engine
├── ui/                # Python Flask web interface
├── helm/              # Helm chart for Kubernetes deployment
├── scripts/           # Developer utility scripts
├── docker-compose.yml # Local development stack
└── .github/           # GitHub Actions CI/CD workflows
```

---

## Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/beeper.git
cd beeper
```

### 2. Run the Setup Script

The setup script installs dependencies and configures the local development environment:

```bash
./scripts/setup-dev.sh
```

### 3. Start the Local Infrastructure Stack

This starts Qdrant (vector database) on ports `6333` (HTTP) and `6334` (gRPC):

```bash
docker-compose up -d
```

Qdrant version: **v1.15.0**

### 4. Initialize Qdrant Collections

Seed the knowledge base with sample data and create the required collections (`investigations` and `knowledge`):

```bash
./scripts/seed-kb.sh
```

### 5. Configure Environment Files

Each component requires its own `.env` file. Copy the provided examples and populate values as needed:

```bash
cp investigator/.env.example investigator/.env
cp ui/.env.example ui/.env
```

See the [Environment Variables](#environment-variables) section for a full reference.

---

## Running Components

Each component runs independently. Start them in separate terminal sessions.

### Operator (Rust)

The operator is the core Kubernetes controller and ingestion service.

```bash
cd operator && cargo run
```

**Exposed endpoints:**

| Port | Path | Description |
|------|------|-------------|
| 8080 | `/healthz` | Liveness probe |
| 8080 | `/readyz` | Readiness probe |
| 8080 | `/api/v1/sources` | Data source management |
| 8080 | `/api/v1/health/components` | Component health status |
| 9090 | — | Metrics and alert ingestion |

### Investigator (Python)

The investigator runs AI-powered incident analysis using your configured LLM provider.

```bash
cd investigator
poetry install
poetry run python -m beeper_investigator.main
```

Before running, ensure your `investigator/.env` is populated with valid LLM credentials. See [Investigator Environment Variables](#investigator-env).

### UI (Flask)

The web interface for interacting with the Beeper platform.

```bash
cd ui
poetry install
poetry run flask run
```

The UI is available at **http://localhost:5000** by default.

Before running, ensure your `ui/.env` is populated. See [UI Environment Variables](#ui-env).

---

## Environment Variables

### Investigator (`investigator/.env`) {#investigator-env}

| Variable | Description | Required |
|----------|-------------|----------|
| `BEEPER_LLM_PROVIDER` | LLM provider name (`anthropic`, `openai`, `azure`, `ollama`) | Yes |
| `BEEPER_LLM_MODEL` | Model identifier (e.g., `claude-opus-4-6`, `gpt-4o`) | Yes |
| `BEEPER_LLM_API_KEY` | API key for the configured provider | Yes |
| `BEEPER_LLM_ENDPOINT` | Custom API endpoint URL (optional, for Azure or self-hosted) | No |
| `BEEPER_LLM_DAILY_CAP_CENTS` | Daily LLM spending cap in cents | No |
| `BEEPER_LLM_MONTHLY_CAP_CENTS` | Monthly LLM spending cap in cents | No |

### UI (`ui/.env`) {#ui-env}

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Flask environment (`development`, `production`) | — |
| `BEEPER_OPERATOR_URL` | URL of the operator API | `http://localhost:8080` |
| `BEEPER_OPERATOR_TIMEOUT` | Operator API request timeout in seconds | `5.0` |
| `BEEPER_UI_PORT` | Port the UI listens on | `5000` |

### Operator (process environment)

| Variable | Description | Default |
|----------|-------------|---------|
| `BEEPER_INGESTION_PORT` | Ingestion HTTP listener port | `9090` |
| `BEEPER_INGESTION_BUFFER_SIZE` | Maximum number of buffered samples | `10000` |

### LLM Spending Caps

To prevent runaway LLM costs during development, configure spending caps in `investigator/.env`:

```dotenv
BEEPER_LLM_DAILY_CAP_CENTS=500    # $5.00 daily limit
BEEPER_LLM_MONTHLY_CAP_CENTS=5000  # $50.00 monthly limit
```

---

## Testing

Beeper has a total of **1,032 tests** across all components.

| Component | Framework | Test Count |
|-----------|-----------|-----------|
| Operator (Rust) | `cargo test` | 162 |
| Investigator (Python) | `pytest` | 375 |
| UI (Python) | `pytest` | 495 |

### Run All Tests

**Operator:**

```bash
cd operator && cargo test
```

**Investigator:**

```bash
cd investigator && poetry run pytest
```

**UI:**

```bash
cd ui && poetry run pytest
```

### Running a Subset of Tests

To run a specific test file or test case in Python:

```bash
# Run a specific file
poetry run pytest tests/test_analysis.py

# Run a specific test by name
poetry run pytest -k "test_investigation_creates_report"
```

For Rust, filter by test name:

```bash
cargo test test_ingestion_buffer
```

---

## Linting and Formatting

All lint and format checks must pass before merging. The CI pipeline enforces these automatically.

### Rust

```bash
# Check formatting
cd operator && cargo fmt --check

# Run Clippy (linter), treating all warnings as errors
cd operator && cargo clippy -- -D warnings
```

To auto-fix formatting:

```bash
cd operator && cargo fmt
```

### Python (Investigator and UI)

Both Python components use [Ruff](https://docs.astral.sh/ruff/) for linting:

```bash
# Investigator
cd investigator && poetry run ruff check .

# UI
cd ui && poetry run ruff check .
```

To auto-fix Ruff issues where possible:

```bash
poetry run ruff check . --fix
```

---

## Type Checking

Both Python components use [mypy](https://mypy.readthedocs.io/) in strict mode.

```bash
# Investigator
cd investigator && poetry run mypy .

# UI
cd ui && poetry run mypy .
```

All new code must pass strict mypy checks. Use Pydantic models for data validation and ensure all public function signatures include type annotations.

---

## Building Docker Images

Build images locally for integration testing or to validate Dockerfile changes:

```bash
# Operator
docker build -t beeper-operator:dev ./operator

# Investigator
docker build -t beeper-investigator:dev ./investigator

# UI
docker build -t beeper-ui:dev ./ui
```

Production images are built and published automatically by the [release workflow](#releases).

---

## CI/CD

### Continuous Integration

The CI pipeline runs on every push and pull request targeting `main`.

**Jobs:**

| Job | Steps |
|-----|-------|
| Rust Operator | `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` |
| Python Investigator | `ruff check`, `pytest` |
| Python UI | `ruff check`, `pytest` |
| Helm Lint | `helm lint` on the chart |

All jobs must pass before a pull request can be merged.

### Releases

The release workflow triggers on tags matching `v*` (e.g., `v1.2.0`).

**Steps:**

1. Builds all three Docker images using Docker Buildx
2. Pushes images to GitHub Container Registry (`ghcr.io`)
3. Uses GitHub Actions layer caching to accelerate builds

**Published images:**

```
ghcr.io/your-org/beeper-operator:<tag>
ghcr.io/your-org/beeper-investigator:<tag>
ghcr.io/your-org/beeper-ui:<tag>
```

To trigger a release, create and push a version tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

---

## Code Conventions

Consistency across the codebase is enforced by linters and code review. Follow these conventions in all contributions.

### Naming

- **JSON fields:** `snake_case` everywhere
- **Rust structs:** Use `#[serde(rename_all = "snake_case")]` on all serializable types
- **Python models:** Use Pydantic with `snake_case` fields (native Python convention)

### API Design

- All endpoints are prefixed with `/api/v1/`
- Resource names use plural nouns (e.g., `/api/v1/sources`, not `/api/v1/source`)
- Errors follow [RFC 7807](https://datatracker.ietf.org/doc/html/rfc7807) Problem Details format

**Example RFC 7807 error response:**

```json
{
  "type": "https://beeper.dev/errors/not-found",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Source with id 'abc123' does not exist."
}
```

### Timestamps

All timestamps must be ISO 8601 formatted in UTC:

```
2026-03-08T14:32:00Z
```

### Structured Logging

All log output must be structured JSON. Every log entry must include the following fields:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC timestamp |
| `level` | Log level (`debug`, `info`, `warn`, `error`) |
| `component` | Name of the emitting component |
| `message` | Human-readable log message |

**Example:**

```json
{
  "timestamp": "2026-03-08T14:32:00Z",
  "level": "info",
  "component": "investigator",
  "message": "Investigation complete",
  "investigation_id": "inv-001",
  "duration_ms": 4210
}
```

---

## Useful Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup-dev.sh` | Full local development environment setup |
| `scripts/generate-clients.sh` | Generate API clients from the OpenAPI specification |
| `scripts/seed-kb.sh` | Seed the knowledge base with sample data and initialize Qdrant collections |
| `scripts/seed_kb.py` | Python implementation of the KB seeder |
| `scripts/init-collections.py` | Initialize Qdrant collections without seeding data |
| `scripts/local-testing.sh` | Run the full local test suite across all components |
| `scripts/demo.sh` | Run a scripted demonstration of the platform |

---

## Contributing

Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a pull request.

### Branch Naming

| Prefix | Use case |
|--------|---------|
| `feature/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Code refactoring without behavior change |

**Examples:**

```
feature/add-pagerduty-source
fix/investigator-timeout-handling
docs/update-development-guide
refactor/operator-ingestion-buffer
```

### Commit Messages

- Use imperative mood ("Add", "Fix", "Remove", not "Added" or "Fixes")
- Keep the first line under 72 characters
- Add a blank line before the body if additional context is needed

**Good examples:**

```
Add PagerDuty alert source integration

Fix race condition in ingestion buffer flush

Remove deprecated v0 API endpoints
```

### Pull Request Checklist

Before marking a PR ready for review, confirm:

- [ ] All CI jobs pass (lint, type check, tests)
- [ ] New code includes tests
- [ ] New public APIs are documented
- [ ] Environment variable changes are reflected in `.env.example` files
- [ ] Structured logging is used (no unstructured `print` or `println!` in production paths)
- [ ] Timestamps use ISO 8601 UTC format
- [ ] API changes follow `/api/v1/` conventions and RFC 7807 error format
