"""Service dependency topology investigation step.

Discovers service-to-service dependencies from Kubernetes service
definitions, endpoints, and ServiceLevel CRDs. Classifies upstream
and downstream relationships and calculates blast radius (FR45).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.steps import StepResult

if TYPE_CHECKING:
    from beeper_investigator.llm.client import LlmClient

logger = logging.getLogger(__name__)

MAX_DEPENDENCY_DEPTH = 2

_BEEPER_GROUP = "beeper.dev"
_BEEPER_VERSION = "v1"
_SERVICELEVEL_PLURAL = "servicelevels"
_INVESTIGATION_PLURAL = "investigations"

_NO_TOPOLOGY_SUMMARY = "No services discovered in namespace — topology unavailable"


class ServiceTopologyStep:
    """Discover and classify service dependency topology.

    Queries K8s Services, Endpoints, and ServiceLevel CRDs to build
    a dependency graph, classify upstream/downstream relationships,
    and calculate blast radius for the investigated service.
    """

    name: str = "Service Topology"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any],
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata
        self._core_api: client.CoreV1Api | None = None
        self._custom_api: client.CustomObjectsApi | None = None

    def _init_k8s(self) -> None:
        """Initialize K8s API clients with in-cluster or kubeconfig fallback."""
        if self._core_api is not None:
            return
        try:
            config.load_incluster_config()
        except config.ConfigException:
            logger.warning("In-cluster config not found, falling back to kubeconfig")
            config.load_kube_config()
        self._core_api = client.CoreV1Api()
        self._custom_api = client.CustomObjectsApi()

    def execute(self) -> StepResult:
        """Run the service topology discovery step."""
        self.status_updater.update_message(
            "Discovering service dependency topology"
        )
        logger.info(
            "Starting topology discovery for service=%s namespace=%s",
            self.context.service,
            self.context.namespace,
        )

        try:
            self._init_k8s()
        except Exception as exc:
            logger.warning("Failed to initialize K8s client: %s", exc)
            return StepResult(
                success=True,
                summary=_NO_TOPOLOGY_SUMMARY,
                data={
                    "service_topology": {},
                    "topology_discovery_attempted": True,
                },
            )

        services = self._discover_services()
        if not services:
            return StepResult(
                success=True,
                summary=_NO_TOPOLOGY_SUMMARY,
                data={
                    "service_topology": {},
                    "topology_discovery_attempted": True,
                },
            )

        dependencies = self._discover_dependencies(services)
        health = self._get_service_health()
        classification = self._classify_topology(services, dependencies)

        topology = {
            "subject_service": self.context.service,
            "upstream": classification["upstream"],
            "downstream": classification["downstream"],
            "all_services": [s["name"] for s in services],
            "dependencies": dependencies,
            "health": health,
            "blast_radius": classification["blast_radius"],
            "discovery_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        summary = self._format_topology_summary(topology)
        logger.info(
            "Topology discovery complete: %d services, %d dependencies, blast_radius=%d",
            len(services),
            len(dependencies),
            classification["blast_radius"],
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "service_topology": topology,
                "topology_discovery_attempted": True,
            },
        )

    def _discover_services(self) -> list[dict[str, Any]]:
        """Discover all services in the investigation namespace.

        Returns:
            List of service info dicts with name, namespace, labels,
            selectors, ports, and cluster_ip.
        """
        assert self._core_api is not None
        try:
            svc_list = self._core_api.list_namespaced_service(
                namespace=self.context.namespace
            )
        except ApiException as exc:
            logger.warning("Failed to list services in namespace %s: %s",
                           self.context.namespace, exc)
            return []

        results: list[dict[str, Any]] = []
        for svc in svc_list.items:
            spec = svc.spec
            results.append({
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "labels": dict(svc.metadata.labels or {}),
                "selectors": dict(spec.selector or {}),
                "ports": [
                    {"port": p.port, "target_port": p.target_port, "protocol": p.protocol}
                    for p in (spec.ports or [])
                ],
                "cluster_ip": spec.cluster_ip or "",
            })
        return results

    def _discover_dependencies(
        self, services: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Discover service-to-service dependencies via Endpoints.

        Examines endpoints to find which pods back each service, then
        cross-references pod env vars and ConfigMaps for service references.

        Returns:
            List of dependency dicts with source_service, target_service,
            dependency_type, and port.
        """
        assert self._core_api is not None
        dependencies: list[dict[str, Any]] = []
        service_names = {s["name"] for s in services}
        service_by_selector: dict[str, str] = {}
        for svc in services:
            for key, val in svc["selectors"].items():
                service_by_selector[f"{key}={val}"] = svc["name"]

        # Examine endpoints for cross-service references
        try:
            endpoints_list = self._core_api.list_namespaced_endpoints(
                namespace=self.context.namespace
            )
        except ApiException as exc:
            logger.warning("Failed to list endpoints: %s", exc)
            return dependencies

        seen: set[tuple[str, str]] = set()

        for ep in endpoints_list.items:
            ep_name = ep.metadata.name
            if ep_name not in service_names:
                continue

            for subset in (ep.subsets or []):
                for address in (subset.addresses or []):
                    target_ref = address.target_ref
                    if target_ref and target_ref.kind == "Pod":
                        pod_name = target_ref.name
                        # Check pod env vars for references to other services
                        pod_deps = self._get_pod_service_references(
                            pod_name, service_names
                        )
                        for dep_service, dep_type in pod_deps:
                            pair = (ep_name, dep_service)
                            if pair not in seen and ep_name != dep_service:
                                seen.add(pair)
                                dependencies.append({
                                    "source_service": ep_name,
                                    "target_service": dep_service,
                                    "dependency_type": dep_type,
                                    "port": subset.ports[0].port
                                    if subset.ports
                                    else None,
                                })

        return dependencies

    def _get_pod_service_references(
        self, pod_name: str, service_names: set[str]
    ) -> list[tuple[str, str]]:
        """Find references to other services in a pod's environment variables.

        Matches service names as hostnames (e.g., ``http://orders:8080``,
        ``orders.default.svc``) rather than plain substrings to avoid false
        positives (e.g., service "db" matching "DEBUG=true").

        Returns:
            List of (service_name, dependency_type) tuples.
        """
        assert self._core_api is not None
        refs: list[tuple[str, str]] = []
        try:
            pod = self._core_api.read_namespaced_pod(
                name=pod_name, namespace=self.context.namespace
            )
        except ApiException:
            return refs

        # Delimiters that indicate a service name is used as a hostname
        _HOST_DELIMITERS = ("://", ":", ".", "/")

        for container in pod.spec.containers or []:
            for env_var in container.env or []:
                if env_var.value:
                    for svc_name in service_names:
                        # Match as hostname: preceded by :// or start,
                        # followed by : . / or end
                        val = env_var.value
                        idx = val.find(svc_name)
                        while idx != -1:
                            before_ok = idx == 0 or val[idx - 1] in (":", "/", "@")
                            end_idx = idx + len(svc_name)
                            after_ok = (
                                end_idx == len(val)
                                or val[end_idx] in (":", ".", "/", ",", " ")
                            )
                            if before_ok and after_ok:
                                refs.append((svc_name, "env_var"))
                                break
                            idx = val.find(svc_name, idx + 1)
        return refs

    def _get_service_health(self) -> dict[str, dict[str, Any]]:
        """Get health status for all services from ServiceLevel CRDs.

        Returns:
            Dict mapping service name to health info with slo_status,
            has_active_investigation, and burn_rate.
        """
        assert self._custom_api is not None
        health: dict[str, dict[str, Any]] = {}

        # Query ServiceLevel CRDs for SLO health
        try:
            slo_list = self._custom_api.list_namespaced_custom_object(
                group=_BEEPER_GROUP,
                version=_BEEPER_VERSION,
                namespace=self.context.namespace,
                plural=_SERVICELEVEL_PLURAL,
            )
            for item in slo_list.get("items", []):
                service_name = item.get("spec", {}).get("service", "")
                status = item.get("status", {})
                burn_rate = status.get("burnRate")
                compliance = status.get("compliance", 1.0)

                slo_status = "healthy"
                if isinstance(burn_rate, (int, float)) and burn_rate > 10:
                    slo_status = "critical"
                elif isinstance(burn_rate, (int, float)) and burn_rate > 1:
                    slo_status = "warning"
                elif isinstance(compliance, (int, float)) and compliance < 0.95:
                    slo_status = "warning"

                health[service_name] = {
                    "slo_status": slo_status,
                    "has_active_investigation": False,
                    "burn_rate": burn_rate,
                }
        except ApiException as exc:
            logger.warning("Failed to query ServiceLevel CRDs: %s", exc)

        # Query Investigation CRDs for active investigations
        try:
            inv_list = self._custom_api.list_namespaced_custom_object(
                group=_BEEPER_GROUP,
                version=_BEEPER_VERSION,
                namespace=self.context.namespace,
                plural=_INVESTIGATION_PLURAL,
            )
            for item in inv_list.get("items", []):
                inv_status = item.get("status", {}).get("phase", "")
                service_name = item.get("spec", {}).get("service", "")
                if inv_status == "investigating" and service_name:
                    if service_name not in health:
                        health[service_name] = {
                            "slo_status": "healthy",
                            "has_active_investigation": True,
                            "burn_rate": None,
                        }
                    else:
                        health[service_name]["has_active_investigation"] = True
        except ApiException as exc:
            logger.warning("Failed to query Investigation CRDs: %s", exc)

        return health

    def _classify_topology(
        self,
        services: list[dict[str, Any]],
        dependencies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Classify services as upstream or downstream of the subject service.

        Uses dependency graph traversal up to MAX_DEPENDENCY_DEPTH.

        Returns:
            Dict with upstream list, downstream list, and blast_radius count.
        """
        subject = self.context.service

        # Build adjacency lists
        # forward: source -> [targets] (source depends on targets)
        forward: dict[str, list[str]] = {}
        # reverse: target -> [sources] (target is depended on by sources)
        reverse: dict[str, list[str]] = {}

        for dep in dependencies:
            src = dep["source_service"]
            tgt = dep["target_service"]
            forward.setdefault(src, []).append(tgt)
            reverse.setdefault(tgt, []).append(src)

        # Upstream: services that the subject depends on (follow forward edges)
        upstream = self._bfs(subject, forward, MAX_DEPENDENCY_DEPTH)

        # Downstream: services that depend on the subject (follow reverse edges)
        downstream = self._bfs(subject, reverse, MAX_DEPENDENCY_DEPTH)

        return {
            "upstream": sorted(upstream),
            "downstream": sorted(downstream),
            "blast_radius": len(downstream),
        }

    @staticmethod
    def _bfs(
        start: str,
        adjacency: dict[str, list[str]],
        max_depth: int,
    ) -> list[str]:
        """Breadth-first traversal up to max_depth."""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start, 0)])

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited and neighbor != start:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        return list(visited)

    def _format_topology_summary(self, topology: dict[str, Any]) -> str:
        """Generate a human-readable topology summary."""
        subject = topology["subject_service"]
        upstream = topology["upstream"]
        downstream = topology["downstream"]
        blast_radius = topology["blast_radius"]

        parts: list[str] = [
            f"Service {subject}: {len(upstream)} upstream, "
            f"{len(downstream)} downstream dependencies"
        ]

        if blast_radius > 0:
            parts.append(f"Blast radius: {blast_radius} services potentially affected")

        health = topology.get("health", {})
        unhealthy = [
            name for name, info in health.items()
            if info.get("slo_status") in ("warning", "critical")
            or info.get("has_active_investigation")
        ]
        if unhealthy:
            parts.append(f"Unhealthy services: {', '.join(sorted(unhealthy))}")

        return ". ".join(parts)
