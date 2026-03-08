# Beeper Documentation Index

**Project:** Beeper — Agentic AI SRE Platform
**Version:** 0.1.0 (MVP)
**Generated:** 2026-03-08
**Scan Level:** Deep

---

## Documentation Suite

| Document | Description |
|----------|-------------|
| [Project Overview](project-overview.md) | Executive summary, technology stack, architecture pattern, repository structure, Qdrant collections, and project status |
| [Source Tree Analysis](source-tree-analysis.md) | Annotated directory tree, critical folder deep-dives, entry points, key patterns, cross-component data flow, and test coverage map |
| [Integration Architecture](integration-architecture.md) | Component communication patterns, API reference, CRD definitions, Qdrant collections, deployment topology, and security considerations |
| [API Contracts](api-contracts.md) | Full API contract reference — data models, Operator REST API (port 8080), Ingestion API (port 9090), UI routes, error format (RFC 7807), and conventions |
| [Development Guide](development-guide.md) | Prerequisites, local setup, running components, environment variables, testing (1,032 tests), linting, CI/CD, code conventions, and contributing |
| [Deployment Guide](deployment-guide.md) | Kubernetes prerequisites, Helm installation, configuration reference, data sources, LLM providers, RBAC, health probes, ingestion endpoints, and troubleshooting |

---

## Quick Links

### For Developers

- **Getting started:** [Development Guide — Local Setup](development-guide.md#local-development-setup)
- **Running tests:** [Development Guide — Testing](development-guide.md#testing)
- **Code conventions:** [Development Guide — Code Conventions](development-guide.md#code-conventions)
- **Entry points:** [Source Tree Analysis — Entry Points](source-tree-analysis.md#entry-points)

### For Operators

- **Deploy Beeper:** [Deployment Guide — Quick Start](deployment-guide.md#quick-start)
- **Configure LLM:** [Deployment Guide — LLM Provider Configuration](deployment-guide.md#llm-provider-configuration)
- **Register sources:** [Deployment Guide — Configuring Data Sources](deployment-guide.md#configuring-data-sources)
- **Troubleshooting:** [Deployment Guide — Troubleshooting](deployment-guide.md#troubleshooting)

### For Integrators

- **API reference:** [API Contracts — Operator REST API](api-contracts.md#operator-rest-api-port-8080)
- **Ingestion protocols:** [API Contracts — Ingestion API](api-contracts.md#ingestion-api-port-9090)
- **Data models:** [API Contracts — Data Models](api-contracts.md#data-models)
- **Communication patterns:** [Integration Architecture — Communication Patterns](integration-architecture.md#communication-patterns)

---

## Repository Structure

```
beeper/
├── operator/       Rust K8s operator — anomaly detection, data ingestion, pod spawning
├── investigator/   Python AI agent — signal correlation, RCA, KB documentation
├── ui/             Flask web interface — investigations, KB wiki, dashboards
├── helm/           Helm chart — CRDs, RBAC, StatefulSets, deployment packaging
├── openapi/        OpenAPI 3.1 specification
├── scripts/        Developer utility scripts
└── docs/           ← You are here
```

---

## Project Status

- **Phase:** MVP Complete (v0.1.0)
- **Epics:** 6/6 complete
- **Stories:** 39/39 done
- **Tests:** 1,032 (162 Rust + 375 Python investigator + 495 Python UI)
- **Functional Requirements:** 47/47 (100%)
- **Non-Functional Requirements:** 16/16 MVP NFRs met
- **Architecture Compliance:** 11/11 decisions implemented
