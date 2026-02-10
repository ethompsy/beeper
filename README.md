# Beeper

Beeper is an open-source agentic AI SRE platform that investigates production anomalies, correlates signals across observability layers, and generates root cause hypotheses with resolution recommendations.

## Architecture

```
beeper/
├── operator/           # Rust K8s operator (Cargo.toml)
├── investigator/       # Python investigator agent (pyproject.toml)
├── ui/                 # Flask web UI (pyproject.toml)
├── openapi/            # OpenAPI specification
├── helm/               # Helm chart for deployment
├── scripts/            # Development scripts
└── docker-compose.yaml # Local development stack
```

## Components

| Component | Technology | Description |
|-----------|------------|-------------|
| **Operator** | Rust + kube-rs | Kubernetes controller that watches for anomalies and spawns investigators |
| **Investigator** | Python | AI agent that correlates signals and generates RCA hypotheses |
| **UI** | Flask + HTMX | Web interface for viewing investigations and managing knowledge base |

## Getting Started

### Prerequisites

- Rust (stable)
- Python 3.11+
- Poetry 1.7+
- Docker and Docker Compose
- Kubernetes cluster (for production deployment)

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/beeper.git
   cd beeper
   ```

2. Run the setup script:
   ```bash
   ./scripts/setup-dev.sh
   ```

3. Start the local development stack:
   ```bash
   docker-compose up -d
   ```

4. Initialize Qdrant collections and seed sample data:
   ```bash
   ./scripts/seed-kb.sh
   ```

   This creates the `investigations` and `knowledge` collections with sample runbooks and investigation entries.

5. Run each component:
   ```bash
   # Operator
   cd operator && cargo run

   # Investigator
   cd investigator && poetry run python -m beeper_investigator.main

   # UI
   cd ui && poetry run flask run
   ```

## Development

### Running Tests

```bash
# Rust operator
cd operator && cargo test

# Python investigator
cd investigator && poetry run pytest

# Python UI
cd ui && poetry run pytest
```

### Linting

```bash
# Rust
cd operator && cargo fmt --check && cargo clippy

# Python
cd investigator && poetry run ruff check .
cd ui && poetry run ruff check .
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
