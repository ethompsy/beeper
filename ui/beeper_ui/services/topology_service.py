"""Service dependency topology service.

Aggregates topology data from investigation findings stored in Qdrant
and provides service dependency graphs for the standalone topology view
and investigation detail integration (FR45).
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"


class TopologyServiceError(Exception):
    """Raised when topology data cannot be retrieved."""


@dataclass
class ServiceNode:
    """A service in the topology graph."""

    name: str
    slo_status: str = "healthy"  # healthy, warning, critical
    has_active_investigation: bool = False
    burn_rate: float | None = None
    upstream_count: int = 0
    downstream_count: int = 0


@dataclass
class ServiceDependency:
    """A dependency edge between two services."""

    source_service: str
    target_service: str
    dependency_type: str = "endpoint"
    port: int | None = None


class TopologyService:
    """Service for aggregating topology data from Qdrant investigations."""

    def __init__(self, qdrant_url: str | None = None) -> None:
        self._qdrant_client: QdrantClient | None = None
        self._qdrant_url = qdrant_url

    @property
    def qdrant_client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            if self._qdrant_url:
                self._qdrant_client = QdrantClient(url=self._qdrant_url)
            else:
                host = os.getenv("QDRANT_HOST", "localhost")
                port = int(os.getenv("QDRANT_PORT", "6333"))
                self._qdrant_client = QdrantClient(host=host, port=port)
        return self._qdrant_client

    def close(self) -> None:
        """Close the Qdrant client."""
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None

    def get_all_services_topology(self) -> dict[str, Any]:
        """Aggregate topology data from recent investigations.

        Queries Qdrant for investigations that contain topology data,
        aggregates known services and dependencies, and returns a
        unified topology graph.

        Returns:
            Dict with services list, dependencies list, and metadata.
        """
        try:
            records = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                limit=100,
                with_payload=True,
            )[0]
        except Exception as exc:
            logger.warning("Failed to query Qdrant for topology: %s", exc)
            return {"services": [], "dependencies": [], "active_investigations": {}}

        services_map: dict[str, ServiceNode] = {}
        all_dependencies: list[dict[str, Any]] = []
        active_investigations: dict[str, int] = {}
        seen_deps: set[tuple[str, str]] = set()

        for record in records:
            payload = record.payload or {}

            # Track service from investigation
            service_name = payload.get("service", "")
            status = payload.get("status", "")
            if service_name:
                if service_name not in services_map:
                    services_map[service_name] = ServiceNode(name=service_name)
                if status == "investigating":
                    active_investigations[service_name] = (
                        active_investigations.get(service_name, 0) + 1
                    )
                    services_map[service_name].has_active_investigation = True

            # Extract topology data from findings
            findings = payload.get("findings", {})
            if not isinstance(findings, dict):
                continue

            topology = findings.get("service_topology", {})
            if not isinstance(topology, dict):
                continue

            # Merge health data
            health = topology.get("health", {})
            if isinstance(health, dict):
                for svc_name, health_info in health.items():
                    if svc_name not in services_map:
                        services_map[svc_name] = ServiceNode(name=svc_name)
                    if isinstance(health_info, dict):
                        slo = health_info.get("slo_status", "healthy")
                        if slo in ("warning", "critical"):
                            services_map[svc_name].slo_status = slo
                        if health_info.get("has_active_investigation"):
                            services_map[svc_name].has_active_investigation = True
                        burn = health_info.get("burn_rate")
                        if isinstance(burn, (int, float)):
                            services_map[svc_name].burn_rate = burn

            # Merge all discovered services
            for svc_name in topology.get("all_services", []):
                if isinstance(svc_name, str) and svc_name not in services_map:
                    services_map[svc_name] = ServiceNode(name=svc_name)

            # Merge dependencies
            for dep in topology.get("dependencies", []):
                if not isinstance(dep, dict):
                    continue
                src = dep.get("source_service", "")
                tgt = dep.get("target_service", "")
                pair = (src, tgt)
                if pair not in seen_deps and src and tgt:
                    seen_deps.add(pair)
                    all_dependencies.append(dep)

        # Calculate upstream/downstream counts
        for dep in all_dependencies:
            src = dep.get("source_service", "")
            tgt = dep.get("target_service", "")
            if src in services_map:
                services_map[src].upstream_count += 1
            if tgt in services_map:
                services_map[tgt].downstream_count += 1

        services_list = sorted(services_map.values(), key=lambda s: s.name)

        return {
            "services": services_list,
            "dependencies": all_dependencies,
            "active_investigations": active_investigations,
        }

    def get_service_dependencies(
        self, service_name: str
    ) -> dict[str, Any]:
        """Get topology data for a specific service.

        Queries the most recent investigation involving the service
        and extracts upstream/downstream dependencies.

        Returns:
            Dict with upstream, downstream, health, and blast_radius.
        """
        try:
            records = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter={
                    "must": [
                        {"key": "service", "match": {"value": service_name}}
                    ]
                },
                limit=10,
                with_payload=True,
            )[0]
        except Exception as exc:
            logger.warning(
                "Failed to query Qdrant for service %s topology: %s",
                service_name, exc,
            )
            return {"upstream": [], "downstream": [], "health": {}, "blast_radius": 0}

        # Find the most recent investigation with topology data
        for record in records:
            payload = record.payload or {}
            findings = payload.get("findings", {})
            if not isinstance(findings, dict):
                continue
            topology = findings.get("service_topology", {})
            if isinstance(topology, dict) and topology.get("subject_service"):
                return {
                    "upstream": topology.get("upstream", []),
                    "downstream": topology.get("downstream", []),
                    "health": topology.get("health", {}),
                    "blast_radius": topology.get("blast_radius", 0),
                }

        return {"upstream": [], "downstream": [], "health": {}, "blast_radius": 0}


_topology_service: TopologyService | None = None


def get_topology_service() -> TopologyService:
    """Get or create the singleton TopologyService instance."""
    global _topology_service
    if _topology_service is None:
        _topology_service = TopologyService()
    return _topology_service
