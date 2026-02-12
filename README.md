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

2. Create the LLM credentials secret (see [LLM Configuration](#llm-configuration) below):
   ```bash
   kubectl create secret generic llm-credentials \
     --from-literal=api-key=YOUR_API_KEY
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

### Streaming Data Ingestion

The operator accepts pushed metrics and logs via streaming ingestion endpoints on port 9090:

#### Prometheus Remote Write

Configure Prometheus to push metrics to Beeper:

```yaml
# prometheus.yml
remote_write:
  - url: http://beeper-operator:9090/api/v1/write
```

The endpoint accepts:
- **Method:** POST
- **Path:** `/api/v1/write`
- **Content-Type:** `application/x-protobuf`
- **Content-Encoding:** `snappy` (recommended)
- **Body:** Snappy-compressed protobuf `WriteRequest`

#### Loki Push

Configure Loki to push logs to Beeper:

```yaml
# loki.yaml (custom client or Promtail)
clients:
  - url: http://beeper-operator:9090/loki/api/v1/push
```

The endpoint accepts:
- **Method:** POST
- **Path:** `/loki/api/v1/push`
- **Content-Type:** `application/json`
- **Content-Encoding:** `snappy` (optional)
- **Body:** JSON with streams array

Example JSON format:
```json
{
  "streams": [
    {
      "stream": {"app": "myapp", "level": "error"},
      "values": [
        ["1676466135000000000", "log line content"]
      ]
    }
  ]
}
```

#### Backpressure Handling

The ingestion endpoints implement backpressure:

| Response Code | Meaning | Action |
|---------------|---------|--------|
| 200 OK (Prometheus) | Success | Continue sending |
| 204 No Content (Loki) | Success | Continue sending |
| 503 Service Unavailable | Buffer full | Retry with backoff |
| 429 Too Many Requests | Rate limited | Retry with backoff |
| 400 Bad Request | Invalid format | Fix request format |

#### Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BEEPER_INGESTION_PORT` | `9090` | Ingestion HTTP port |
| `BEEPER_INGESTION_BUFFER_SIZE` | `10000` | Max buffered samples |

### Health Endpoints

The operator exposes health endpoints on port 8080:

- `/healthz` - Liveness probe (always returns 200 OK)
- `/readyz` - Readiness probe (checks Kubernetes API connectivity)

### API Endpoints

The operator exposes UI-facing API endpoints on port 8080:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sources` | GET | List all configured sources with status |
| `/api/v1/health/components` | GET | Component health status |
| `/api/v1/ingestion/stats` | GET | Ingestion buffer statistics |

### LLM Configuration

Beeper uses LLM providers for AI-powered root cause analysis. Configuration is done via Helm values and Kubernetes Secrets.

#### Supported Providers

| Provider | Model Examples | API Key Required |
|----------|---------------|------------------|
| **Anthropic** | `claude-sonnet-4`, `claude-3-haiku`, `claude-opus-4` | Yes |
| **OpenAI** | `gpt-4o`, `gpt-4-turbo` | Yes |
| **Azure OpenAI** | `azure/<deployment-name>` | Yes (+ endpoint) |
| **Ollama** | `ollama/llama3` | No |

#### Creating the LLM Secret

```bash
# For Anthropic (default)
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_ANTHROPIC_API_KEY

# For OpenAI
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_OPENAI_API_KEY

# For Azure OpenAI
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_AZURE_API_KEY
```

Or use the example manifest:

```bash
# Edit helm/beeper/examples/llm-secret.yaml with your key
kubectl apply -f helm/beeper/examples/llm-secret.yaml
```

#### Helm Configuration

Configure the LLM provider in `values.yaml`:

```yaml
llm:
  provider: anthropic          # anthropic, openai, azure, ollama
  model: claude-sonnet-4       # Model identifier
  apiKeySecret: llm-credentials  # Secret name
  apiKeySecretKey: api-key     # Key within secret
  # endpoint: ""               # Required for Azure, optional for Ollama
```

#### Health Monitoring

LLM connectivity status is visible in the `/api/v1/health/components` endpoint and the UI Health page. Status values:

| Status | Meaning |
|--------|---------|
| `healthy` | LLM configured and credentials accessible |
| `unconfigured` | LLM provider not configured |
| `unhealthy` | Configuration error (missing secret, invalid model, etc.) |

#### Local Development

For local investigator development, copy `.env.example` to `.env`:

```bash
cd investigator
cp .env.example .env
# Edit .env with your API key
```

Environment variables:
- `BEEPER_LLM_PROVIDER` - Provider name
- `BEEPER_LLM_MODEL` - Model identifier
- `BEEPER_LLM_API_KEY` - API key
- `BEEPER_LLM_ENDPOINT` - Custom endpoint (optional)

### UI Development

The web UI is a Flask application with HTMX for dynamic updates.

#### Running the UI

```bash
cd ui
poetry install
poetry run flask run
```

The UI will be available at http://localhost:5000.

#### Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | Flask environment |
| `BEEPER_OPERATOR_URL` | `http://localhost:8080` | Operator API URL |
| `BEEPER_OPERATOR_TIMEOUT` | `5.0` | API request timeout (seconds) |
| `BEEPER_UI_PORT` | `5000` | UI server port |

#### UI Pages

| Route | Description |
|-------|-------------|
| `/` | Home page |
| `/sources/` | View configured data sources and their status |
| `/health/` | View operator component health |
| `/health/api` | UI health check endpoint |

#### Testing

```bash
cd ui
poetry run pytest -v
poetry run ruff check .
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
