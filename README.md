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

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.26+)
- Helm 3.x
- kubectl configured for your cluster

### Installing Beeper

1. Install the Helm chart:
   ```bash
   helm install beeper ./helm/beeper
   ```

2. Create the LLM credentials secret:
   ```bash
   kubectl create secret generic beeper-llm-credentials \
     --from-literal=api-key=YOUR_ANTHROPIC_API_KEY
   ```

3. Verify the operator is running:
   ```bash
   kubectl get pods -l app.kubernetes.io/component=operator
   kubectl logs -l app.kubernetes.io/component=operator
   ```

### Custom Resources

Beeper uses two Custom Resource Definitions (CRDs):

#### Source CRD

Configure data sources (Prometheus/Loki):

**Prometheus Source:**

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  source_type: prometheus
  endpoint: http://prometheus:9090
  credentials_secret: prometheus-creds  # Optional - for authenticated access
```

**Loki Source:**

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: loki-main
spec:
  source_type: loki
  endpoint: http://loki:3100
  credentials_secret: loki-creds  # Optional - for authenticated access
```

**Credential Secret Format:**

Both Prometheus and Loki sources use the same credential format. If authentication is required, create a Secret with username and password:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: prometheus-creds  # or loki-creds
type: kubernetes.io/basic-auth
data:
  username: <base64-encoded-username>
  password: <base64-encoded-password>
```

**Source Status:**

The operator validates connectivity and updates the Source status:

```bash
kubectl get sources
NAME              TYPE         CONNECTED   AGE
prometheus-main   prometheus   true        5m
```

View detailed status:

```bash
kubectl describe source prometheus-main
```

**Troubleshooting Connection Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| "Connection refused" | Endpoint unreachable | Verify endpoint URL and network policies |
| "Authentication failed" | Invalid credentials | Check Secret username/password are correct |
| "Access forbidden" | Insufficient permissions | Ensure credentials have read access |
| "Connection timed out" | Slow network or overloaded server | Increase timeout or check server health |
| "Secret not found" | Missing credentials Secret | Create the Secret in the same namespace |
| "Prometheus API error" | Invalid PromQL query or API issue | Check Prometheus logs and query syntax |
| "Loki API error" | Invalid LogQL query or API issue | Check Loki logs and query syntax |
| "Invalid response" | Unexpected response format | Ensure source endpoint is correct type |

#### Investigation CRD

Created automatically when anomalies are detected:

```yaml
apiVersion: beeper.dev/v1
kind: Investigation
metadata:
  name: inv-abc123
spec:
  condition: "High error rate detected"
  service: payments
  severity: high
  triggered_at: "2026-02-09T12:00:00Z"
```

### RBAC Permissions

The operator ServiceAccount requires:

| Resource | Verbs |
|----------|-------|
| `sources.beeper.dev` | get, list, watch, create, update, patch, delete |
| `investigations.beeper.dev` | get, list, watch, create, update, patch, delete |
| `sources.beeper.dev/status` | get, update, patch |
| `investigations.beeper.dev/status` | get, update, patch |
| `jobs` (batch) | get, list, watch, create, update, patch, delete |
| `pods` | get, list, watch |
| `secrets` | get, list, watch |
| `configmaps` | get, list, watch |
| `events` | create, patch |

### Health Endpoints

The operator exposes health endpoints on port 8080:

- `/healthz` - Liveness probe (always returns 200 OK)
- `/readyz` - Readiness probe (checks Kubernetes API connectivity)

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
