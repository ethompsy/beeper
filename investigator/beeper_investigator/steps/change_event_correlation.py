"""Change event correlation investigation step.

Ingests and correlates change events (config changes, scaling, DNS, certs)
with anomalies by querying K8s Events API for resource modifications (FR46).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.steps import StepResult

if TYPE_CHECKING:
    from beeper_investigator.llm.client import LlmClient

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 60

# Confidence thresholds in seconds (same as DeployCorrelationStep)
_STRONG_THRESHOLD = 5 * 60  # <5 min
_MODERATE_THRESHOLD = 30 * 60  # 5-30 min

WATCHED_RESOURCE_TYPES = (
    "ConfigMap",
    "Secret",
    "HorizontalPodAutoscaler",
    "Ingress",
    "Certificate",
)

_NO_CHANGE_SUMMARY = "No recent change events found \u2014 likely not config-change-related"

_DEDUP_WINDOW_SECONDS = 60


def _classify_confidence(time_gap_seconds: int) -> str:
    """Classify change event correlation confidence based on time gap."""
    if time_gap_seconds < _STRONG_THRESHOLD:
        return "strong"
    if time_gap_seconds < _MODERATE_THRESHOLD:
        return "moderate"
    return "weak"


def _format_time_gap(seconds: int) -> str:
    """Format a time gap in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds} sec"
    minutes = seconds // 60
    remaining = seconds % 60
    if remaining == 0:
        return f"{minutes} min"
    return f"{minutes} min {remaining} sec"


class ChangeEventCorrelationStep:
    """Correlate anomalies with recent change events.

    Queries K8s Events API for recent changes to ConfigMaps, Secrets,
    HPAs, Ingresses, and cert-manager Certificates, then calculates
    temporal correlation with the anomaly detection time.
    """

    name: str = "Change Event Correlation"

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
        self._autoscaling_api: client.AutoscalingV1Api | None = None
        self._networking_api: client.NetworkingV1Api | None = None
        self._custom_api: client.CustomObjectsApi | None = None

    def _init_k8s(self) -> bool:
        """Initialize K8s API clients. Returns True on success."""
        try:
            config.load_incluster_config()
        except Exception:
            try:
                config.load_kube_config()
            except Exception as exc:
                logger.warning("Failed to load K8s config: %s", exc)
                return False

        self._core_api = client.CoreV1Api()
        self._autoscaling_api = client.AutoscalingV1Api()
        self._networking_api = client.NetworkingV1Api()
        self._custom_api = client.CustomObjectsApi()
        return True

    def execute(self) -> StepResult:
        """Run the change event correlation step."""
        self.status_updater.update_message(
            "Checking for correlated change events..."
        )
        logger.info(
            "Starting change event correlation for service=%s namespace=%s",
            self.context.service,
            self.context.namespace,
        )

        try:
            if not self._init_k8s():
                return StepResult(
                    success=True,
                    summary="Change event correlation skipped — K8s API unavailable",
                    data={
                        "change_events": [],
                        "change_summary": "K8s API unavailable — change event correlation skipped",
                        "change_event_correlation_attempted": True,
                    },
                )

            events = self._fetch_change_events()
            resource_mods = self._fetch_resource_modifications()
            merged = self._merge_and_deduplicate(events, resource_mods)
            correlations = self._correlate_changes(merged)
            summary = self._format_change_summary(correlations)

            event_count = len(merged)
            correlation_count = len(correlations)

            logger.info(
                "Change event correlation complete: %d events found, %d correlations",
                event_count,
                correlation_count,
            )

            return StepResult(
                success=True,
                summary=summary,
                data={
                    "change_events": correlations,
                    "change_summary": summary,
                    "change_event_correlation_attempted": True,
                },
            )
        except Exception as exc:
            logger.warning("Change event correlation failed: %s", exc)
            return StepResult(
                success=False,
                summary="Change event correlation failed",
                error=str(exc),
                data={"change_event_correlation_attempted": True},
            )

    def _fetch_change_events(self) -> list[dict[str, Any]]:
        """Fetch change events from K8s Events API.

        Queries namespaced events and filters for watched resource types
        within the lookback window.
        """
        assert self._core_api is not None

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)
        results: list[dict[str, Any]] = []

        try:
            events = self._core_api.list_namespaced_event(
                namespace=self.context.namespace,
            )
        except ApiException as exc:
            logger.warning(
                "Failed to list events in namespace %s: %s",
                self.context.namespace,
                exc.reason,
            )
            return []

        for event in events.items or []:
            involved = event.involved_object
            if not involved or involved.kind not in WATCHED_RESOURCE_TYPES:
                continue

            # Determine event timestamp
            event_ts = event.last_timestamp or event.event_time
            if event_ts is None:
                continue

            if isinstance(event_ts, str):
                try:
                    event_dt = datetime.fromisoformat(
                        event_ts.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue
            else:
                event_dt = event_ts
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)

            if event_dt < cutoff:
                continue

            results.append({
                "resource_type": involved.kind,
                "namespace": involved.namespace or self.context.namespace,
                "resource_name": involved.name or "unknown",
                "change_description": event.message or "",
                "timestamp": event_dt.isoformat(),
                "reason": event.reason or "",
                "action": getattr(event, "action", "") or "",
            })

        return results

    def _fetch_resource_modifications(self) -> list[dict[str, Any]]:
        """Fetch recent resource modifications by checking managed_fields.

        Queries ConfigMaps, Secrets, HPAs, Ingresses, and cert-manager
        Certificates filtered by service-related labels.
        """
        assert self._core_api is not None

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)
        results: list[dict[str, Any]] = []
        service = self.context.service
        namespace = self.context.namespace

        label_selectors = [
            f"app={service}",
            f"app.kubernetes.io/name={service}",
        ]

        for label_selector in label_selectors:
            results.extend(
                self._check_configmaps(namespace, label_selector, cutoff)
            )
            results.extend(
                self._check_secrets(namespace, label_selector, cutoff)
            )
            results.extend(
                self._check_hpas(namespace, label_selector, cutoff)
            )
            results.extend(
                self._check_ingresses(namespace, label_selector, cutoff)
            )

        results.extend(self._check_certificates(namespace, cutoff))

        return results

    def _check_configmaps(
        self,
        namespace: str,
        label_selector: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """Check ConfigMaps for recent modifications."""
        assert self._core_api is not None
        results: list[dict[str, Any]] = []
        try:
            cms = self._core_api.list_namespaced_config_map(
                namespace=namespace, label_selector=label_selector
            )
            for cm in cms.items or []:
                mod_time = self._get_last_modified(cm.metadata)
                if mod_time and mod_time >= cutoff:
                    results.append({
                        "resource_type": "ConfigMap",
                        "namespace": namespace,
                        "resource_name": cm.metadata.name or "unknown",
                        "change_description": f"ConfigMap {cm.metadata.name} modified",
                        "timestamp": mod_time.isoformat(),
                        "reason": "Modified",
                        "action": "update",
                    })
        except ApiException as exc:
            logger.warning("Failed to list ConfigMaps: %s", exc.reason)
        return results

    def _check_secrets(
        self,
        namespace: str,
        label_selector: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """Check Secrets for recent modifications."""
        assert self._core_api is not None
        results: list[dict[str, Any]] = []
        try:
            secrets = self._core_api.list_namespaced_secret(
                namespace=namespace, label_selector=label_selector
            )
            for secret in secrets.items or []:
                mod_time = self._get_last_modified(secret.metadata)
                if mod_time and mod_time >= cutoff:
                    results.append({
                        "resource_type": "Secret",
                        "namespace": namespace,
                        "resource_name": secret.metadata.name or "unknown",
                        "change_description": f"Secret {secret.metadata.name} modified",
                        "timestamp": mod_time.isoformat(),
                        "reason": "Modified",
                        "action": "update",
                    })
        except ApiException as exc:
            logger.warning("Failed to list Secrets: %s", exc.reason)
        return results

    def _check_hpas(
        self,
        namespace: str,
        label_selector: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """Check HPAs for recent modifications."""
        assert self._autoscaling_api is not None
        results: list[dict[str, Any]] = []
        try:
            hpas = self._autoscaling_api.list_namespaced_horizontal_pod_autoscaler(
                namespace=namespace, label_selector=label_selector
            )
            for hpa in hpas.items or []:
                mod_time = self._get_last_modified(hpa.metadata)
                if mod_time and mod_time >= cutoff:
                    results.append({
                        "resource_type": "HorizontalPodAutoscaler",
                        "namespace": namespace,
                        "resource_name": hpa.metadata.name or "unknown",
                        "change_description": f"HPA {hpa.metadata.name} modified",
                        "timestamp": mod_time.isoformat(),
                        "reason": "Modified",
                        "action": "update",
                    })
        except ApiException as exc:
            logger.warning("Failed to list HPAs: %s", exc.reason)
        return results

    def _check_ingresses(
        self,
        namespace: str,
        label_selector: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """Check Ingresses for recent modifications."""
        assert self._networking_api is not None
        results: list[dict[str, Any]] = []
        try:
            ingresses = self._networking_api.list_namespaced_ingress(
                namespace=namespace, label_selector=label_selector
            )
            for ing in ingresses.items or []:
                mod_time = self._get_last_modified(ing.metadata)
                if mod_time and mod_time >= cutoff:
                    results.append({
                        "resource_type": "Ingress",
                        "namespace": namespace,
                        "resource_name": ing.metadata.name or "unknown",
                        "change_description": f"Ingress {ing.metadata.name} modified",
                        "timestamp": mod_time.isoformat(),
                        "reason": "Modified",
                        "action": "update",
                    })
        except ApiException as exc:
            logger.warning("Failed to list Ingresses: %s", exc.reason)
        return results

    def _check_certificates(
        self, namespace: str, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Check cert-manager Certificates for recent modifications."""
        assert self._custom_api is not None
        results: list[dict[str, Any]] = []
        try:
            certs = self._custom_api.list_namespaced_custom_object(
                group="cert-manager.io",
                version="v1",
                namespace=namespace,
                plural="certificates",
            )
            for cert in certs.get("items", []):
                metadata = cert.get("metadata", {})
                managed = metadata.get("managedFields", [])
                mod_time = self._parse_managed_fields_time(managed)
                if mod_time and mod_time >= cutoff:
                    cert_name = metadata.get("name", "unknown")
                    results.append({
                        "resource_type": "Certificate",
                        "namespace": namespace,
                        "resource_name": cert_name,
                        "change_description": f"Certificate {cert_name} modified",
                        "timestamp": mod_time.isoformat(),
                        "reason": "Modified",
                        "action": "update",
                    })
        except ApiException as exc:
            logger.warning("Failed to list Certificates: %s", exc.reason)
        except Exception as exc:
            logger.warning("Failed to query cert-manager CRDs: %s", exc)
        return results

    def _get_last_modified(self, metadata: Any) -> datetime | None:
        """Extract last modification time from resource metadata."""
        managed_fields = getattr(metadata, "managed_fields", None)
        if managed_fields:
            return self._parse_managed_fields_time(
                [
                    {"time": getattr(f, "time", None)}
                    for f in managed_fields
                    if getattr(f, "time", None)
                ]
            )
        return None

    @staticmethod
    def _parse_managed_fields_time(
        managed_fields: list[dict[str, Any]],
    ) -> datetime | None:
        """Find the most recent time from managed_fields entries."""
        latest: datetime | None = None
        for field_entry in managed_fields:
            ts = field_entry.get("time")
            if ts is None:
                continue
            if isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            else:
                dt = ts
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            if latest is None or dt > latest:
                latest = dt
        return latest

    def _merge_and_deduplicate(
        self,
        events: list[dict[str, Any]],
        resource_mods: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge event-based and resource-based change detection, deduplicating."""
        combined = list(events)
        for mod in resource_mods:
            mod_name = mod["resource_name"]
            mod_ts = mod["timestamp"]
            try:
                mod_dt = datetime.fromisoformat(mod_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                combined.append(mod)
                continue

            duplicate = False
            for existing in events:
                if existing["resource_name"] != mod_name:
                    continue
                try:
                    ex_dt = datetime.fromisoformat(
                        existing["timestamp"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue
                if abs((mod_dt - ex_dt).total_seconds()) < _DEDUP_WINDOW_SECONDS:
                    duplicate = True
                    break

            if not duplicate:
                combined.append(mod)

        return combined

    def _correlate_changes(
        self, change_events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calculate temporal correlation between change events and anomaly.

        For each change event, calculates the time gap between the event
        timestamp and the anomaly detection time, and classifies the
        correlation confidence.
        """
        if not change_events:
            return []

        anomaly_time_str = self.pipeline_metadata.get("anomaly_detected_at")
        if anomaly_time_str:
            try:
                anomaly_time = datetime.fromisoformat(
                    str(anomaly_time_str).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                anomaly_time = datetime.now(timezone.utc)
        else:
            anomaly_time = datetime.now(timezone.utc)

        correlations: list[dict[str, Any]] = []
        for event in change_events:
            event_ts = event["timestamp"]
            try:
                if isinstance(event_ts, str):
                    event_dt = datetime.fromisoformat(
                        event_ts.replace("Z", "+00:00")
                    )
                else:
                    event_dt = event_ts
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Cannot parse change event timestamp %r: %s",
                    event_ts,
                    exc,
                )
                continue

            time_gap = int((anomaly_time - event_dt).total_seconds())
            if time_gap < 0:
                time_gap = 0  # Event in the future (clock skew)

            confidence = _classify_confidence(time_gap)

            correlations.append({
                "resource_type": event["resource_type"],
                "namespace": event["namespace"],
                "resource_name": event["resource_name"],
                "change_description": event["change_description"],
                "timestamp": event_dt.isoformat(),
                "time_gap_seconds": time_gap,
                "confidence": confidence,
                "reason": event.get("reason", ""),
            })

        # Sort by time gap (closest change first)
        correlations.sort(key=lambda c: c["time_gap_seconds"])
        return correlations

    def _format_change_summary(
        self, correlations: list[dict[str, Any]]
    ) -> str:
        """Generate a human-readable change event correlation summary."""
        if not correlations:
            return _NO_CHANGE_SUMMARY

        strong = sum(1 for c in correlations if c["confidence"] == "strong")
        moderate = sum(1 for c in correlations if c["confidence"] == "moderate")
        weak = sum(1 for c in correlations if c["confidence"] == "weak")

        total = len(correlations)
        parts = f"{total} change event{'s' if total != 1 else ''} found within lookback window"
        breakdown = ", ".join(
            f"{n} {label}"
            for n, label in [(strong, "strong"), (moderate, "moderate"), (weak, "weak")]
            if n > 0
        )
        summary = f"{parts} ({breakdown} correlation)"

        # Include strongest correlation detail
        best = correlations[0]
        gap_str = _format_time_gap(best["time_gap_seconds"])
        summary += (
            f". {best['resource_type']} {best['resource_name']}"
            f" changed {gap_str} before anomaly ({best['confidence']} correlation)"
        )

        return summary
