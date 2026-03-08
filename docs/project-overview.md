# Beeper - Project Overview

**Generated:** 2026-03-08
**Scan Level:** Deep
**Repository Type:** Monorepo (4 parts)

## Executive Summary

Beeper is an open-source agentic AI SRE platform that investigates production anomalies, correlates signals across observability layers, and generates root cause hypotheses with resolution recommendations. It operates as a Kubernetes operator that continuously monitors logs and metrics, detects anomalies, spawns AI-powered investigator agents, and maintains a living knowledge base that improves through human collaboration.

**License:** Apache 2.0

## Technology Stack

| Category | Technology | Version | Component |
|----------|------------|---------|-----------|
| **Languages** | Rust (stable, edition 2021) | stable | Operator |
| | Python | ^3.11 | Investigator, UI |
| **K8s Operator** | kube-rs | 0.95 | Operator |
| | kube-runtime | 0.95 | Operator |
| | k8s-openapi | 0.23 (v1_30) | Operator |
| **Async Runtime** | tokio | 1.x (full) | Operator |
| **HTTP Server** | axum | 0.7 | Operator |
| **Web Framework** | Flask | ^3.0 | UI |
| **Frontend** | HTMX + SSE | - | UI |
| **LLM Client** | LiteLLM | ^1.30 | Investigator, UI |
| **LLM Provider** | Anthropic (default) | ^0.18 | Investigator |
| **Vector Database** | Qdrant | v1.15.0 (local) / v1.12.0 (Helm) | All |
| **HTTP Client** | httpx (Python) | ^0.27 | Investigator, UI |
| | reqwest (Rust) | 0.11 | Operator |
| **Data Validation** | Pydantic | ^2.6 | Investigator |
| | serde + schemars | 1.x / 0.8 | Operator |
| **K8s Client (Python)** | kubernetes | ^29.0 | Investigator |
| **Markdown Rendering** | markdown + bleach | ^3.5 / ^6.1 | UI |
| **Serialization** | prost (protobuf) | 0.13 | Operator |
| | snap (snappy compression) | 1.1 | Operator |
| **Error Handling** | thiserror + anyhow | 1.x | Operator |
| **Logging** | tracing + tracing-subscriber | 0.1 / 0.3 | Operator |
| **Date/Time** | chrono | 0.4 | Operator |
| **Package Management** | Cargo | - | Operator |
| | Poetry | 1.7+ | Investigator, UI |
| **Containerization** | Docker | - | All |
| **Orchestration** | Helm 3.x | Chart v0.1.0 | Deployment |
| **CI/CD** | GitHub Actions | - | All |
| **Container Registry** | ghcr.io | - | Release |
| **API Specification** | OpenAPI 3.1 | - | Shared |
| **Linting** | cargo fmt + clippy | - | Operator |
| | ruff | ^0.3 | Investigator, UI |
| **Type Checking** | mypy (strict) | ^1.8 | Investigator, UI |
| **Testing** | cargo test | - | Operator |
| | pytest | ^8.0 | Investigator, UI |
| **Test Mocking** | wiremock | 0.5 | Operator |
| | respx | ^0.21 | UI |

## Architecture Pattern

**Pattern:** Kubernetes Operator + Spawned Agent Jobs + Web UI

```
┌─────────────────────────────────────────────────────────┐
│                     K8s Cluster                          │
│  ┌─────────────────┐                                     │
│  │  beeper-operator │──────┐                              │
│  │     (Rust)       │      │ spawns K8s Job               │
│  └────────┬─────────┘      ▼                              │
│           │         ┌──────────────────┐                  │
│   watches │         │  investigator    │                  │
│   CRDs    │         │   Job (Python)   │──→ LLM API      │
│           │         └────────┬─────────┘                  │
│           │                  │ writes findings             │
│           ▼                  ▼                             │
│  ┌─────────────────┐  ┌──────────────────┐                │
│  │ Source/Invest.   │  │     Qdrant       │                │
│  │ CRDs (status)    │  │  (StatefulSet)   │                │
│  └─────────────────┘  └────────┬─────────┘                │
│                                │ queries                   │
│                                ▼                           │
│                       ┌──────────────────┐                 │
│                       │   beeper-ui      │                 │
│                       │   (Flask+HTMX)   │                 │
│                       └──────────────────┘                 │
└─────────────────────────────────────────────────────────┘
```

## Repository Structure

| Part | Path | Type | Language | Description |
|------|------|------|----------|-------------|
| **Operator** | `operator/` | backend | Rust | K8s controller — anomaly detection, data ingestion, pod spawning |
| **Investigator** | `investigator/` | backend | Python | AI agent — signal correlation, RCA, KB documentation |
| **UI** | `ui/` | web | Python | Flask web interface — investigations, KB wiki, dashboards |
| **Helm** | `helm/` | infra | YAML | K8s deployment packaging — CRDs, RBAC, StatefulSets |

## Key Custom Resources

| CRD | API Group | Description |
|-----|-----------|-------------|
| `Source` | `beeper.dev/v1` | Configures data sources (Prometheus, Loki) |
| `Investigation` | `beeper.dev/v1` | Tracks anomaly investigations (auto-created) |

## Qdrant Collections

| Collection | Purpose | Vector |
|------------|---------|--------|
| `investigations` | Investigation state and findings | Yes (1536d) |
| `knowledge` | KB entries with embeddings | Yes (1536d) |
| `knowledge_versions` | Version snapshots | No (payload-only) |
| `corrections` | Correction conversations | No (payload-only) |
| `learning_patterns` | Diff analysis patterns | No (payload-only) |
| `service_trust_levels` | Per-service trust tracking | No (payload-only) |

## Project Status

- **Phase:** MVP Complete (v0.1.0)
- **Stories:** 39/39 done across 6 epics
- **Tests:** 1,032 (162 Rust, 375 Python investigator, 495 Python UI)
- **FR Coverage:** 47/47 (100%)
- **NFR Coverage:** 16/16 MVP NFRs met
- **Architecture Compliance:** 11/11 decisions implemented as specified
