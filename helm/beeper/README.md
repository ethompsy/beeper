# Beeper Helm Chart

This Helm chart deploys Beeper, an agentic AI SRE platform, on a Kubernetes cluster.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.0+
- Qdrant (included as dependency or external)

## Installation

### Add the chart repository

```bash
helm repo add beeper https://your-org.github.io/beeper
helm repo update
```

### Install the chart

```bash
helm install beeper beeper/beeper
```

### Install with custom values

```bash
helm install beeper beeper/beeper -f my-values.yaml
```

## Configuration

See [values.yaml](values.yaml) for the full list of configuration options.

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `operator.replicaCount` | Number of operator replicas | `1` |
| `ui.replicaCount` | Number of UI replicas | `1` |
| `llm.provider` | LLM provider (anthropic, openai) | `anthropic` |
| `llm.model` | LLM model to use | `claude-3-5-sonnet-20241022` |
| `llm.secretName` | Secret containing API key | `beeper-llm-credentials` |
| `qdrant.enabled` | Enable Qdrant deployment | `true` |
| `qdrant.persistence.size` | Qdrant storage size | `10Gi` |

### Creating the LLM Secret

Before installing, create the secret with your LLM API key:

```bash
kubectl create secret generic beeper-llm-credentials \
  --from-literal=api-key=YOUR_API_KEY
```

## Development

For local development, use the dev values:

```bash
helm install beeper ./helm/beeper -f ./helm/beeper/values-dev.yaml
```

## Uninstallation

```bash
helm uninstall beeper
```

## License

Apache License 2.0
