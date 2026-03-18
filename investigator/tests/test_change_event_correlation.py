"""Tests for ChangeEventCorrelationStep."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from kubernetes.client.rest import ApiException

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.change_event_correlation import (
    _NO_CHANGE_SUMMARY,
    ChangeEventCorrelationStep,
    _classify_confidence,
    _format_time_gap,
)


def _make_context(
    *,
    service: str = "payments",
    namespace: str = "default",
) -> InvestigationContext:
    return InvestigationContext(
        investigation_id="inv-test-001",
        namespace=namespace,
        condition="High error rate on /checkout",
        service=service,
        severity="high",
    )


def _make_step(
    *,
    service: str = "payments",
    namespace: str = "default",
    pipeline_metadata: dict | None = None,
) -> ChangeEventCorrelationStep:
    context = _make_context(service=service, namespace=namespace)
    return ChangeEventCorrelationStep(
        llm_client=MagicMock(),
        context=context,
        status_updater=MagicMock(),
        pipeline_metadata=pipeline_metadata or {},
    )


def _make_k8s_event(
    *,
    kind: str = "ConfigMap",
    name: str = "payments-config",
    namespace: str = "default",
    message: str = "Updated config",
    reason: str = "ConfigUpdated",
    timestamp: datetime | None = None,
) -> MagicMock:
    """Create a mock K8s Event object."""
    event = MagicMock()
    event.involved_object.kind = kind
    event.involved_object.name = name
    event.involved_object.namespace = namespace
    event.message = message
    event.reason = reason
    event.action = ""
    ts = timestamp or datetime.now(timezone.utc) - timedelta(minutes=3)
    event.last_timestamp = ts
    event.event_time = None
    return event


# ── TestClassifyConfidence ──────────────────────────────────────────


class TestClassifyConfidence:
    """Test confidence classification based on time gap."""

    def test_strong_under_5_minutes(self) -> None:
        assert _classify_confidence(0) == "strong"
        assert _classify_confidence(60) == "strong"
        assert _classify_confidence(299) == "strong"

    def test_moderate_5_to_30_minutes(self) -> None:
        assert _classify_confidence(300) == "moderate"
        assert _classify_confidence(900) == "moderate"
        assert _classify_confidence(1799) == "moderate"

    def test_weak_over_30_minutes(self) -> None:
        assert _classify_confidence(1800) == "weak"
        assert _classify_confidence(3600) == "weak"


# ── TestFormatTimeGap ──────────────────────────────────────────────


class TestFormatTimeGap:
    """Test time gap formatting."""

    def test_seconds_only(self) -> None:
        assert _format_time_gap(30) == "30 sec"

    def test_minutes_exact(self) -> None:
        assert _format_time_gap(120) == "2 min"

    def test_minutes_and_seconds(self) -> None:
        assert _format_time_gap(150) == "2 min 30 sec"


# ── TestChangeEventCorrelationStep ──────────────────────────────────


class TestChangeEventCorrelationStep:
    """Test the main ChangeEventCorrelationStep."""

    def test_step_name(self) -> None:
        step = _make_step()
        assert step.name == "Change Event Correlation"

    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_k8s_init_failure_returns_empty(self, mock_config: MagicMock) -> None:
        """When K8s config cannot be loaded, return graceful empty result."""
        mock_config.load_incluster_config.side_effect = Exception("No cluster")
        mock_config.load_kube_config.side_effect = Exception("No kubeconfig")

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["change_events"] == []
        assert result.data["change_event_correlation_attempted"] is True

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_empty_namespace_returns_no_events(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """When namespace has no events, return empty result."""
        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[])
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["change_events"] == []
        assert result.data["change_summary"] == _NO_CHANGE_SUMMARY

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_successful_correlation_with_events(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """When events are found, correlations are calculated."""
        now = datetime.now(timezone.utc)
        event = _make_k8s_event(
            kind="ConfigMap",
            name="payments-config",
            message="Updated TIMEOUT_MS",
            timestamp=now - timedelta(minutes=3),
        )

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[event])
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert len(result.data["change_events"]) == 1
        corr = result.data["change_events"][0]
        assert corr["resource_type"] == "ConfigMap"
        assert corr["resource_name"] == "payments-config"
        assert corr["confidence"] == "strong"

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_k8s_api_error_handled_gracefully(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """When K8s API returns an error, return empty result gracefully."""
        mock_core = MagicMock()
        mock_core.list_namespaced_event.side_effect = ApiException(
            status=403, reason="Forbidden"
        )
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["change_events"] == []

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_multiple_resource_types(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Events from different resource types are all collected."""
        now = datetime.now(timezone.utc)
        cm_event = _make_k8s_event(
            kind="ConfigMap",
            name="payments-config",
            timestamp=now - timedelta(minutes=2),
        )
        secret_event = _make_k8s_event(
            kind="Secret",
            name="payments-secrets",
            timestamp=now - timedelta(minutes=10),
        )
        hpa_event = _make_k8s_event(
            kind="HorizontalPodAutoscaler",
            name="payments-hpa",
            message="Scaled replicas",
            timestamp=now - timedelta(minutes=20),
        )

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(
            items=[cm_event, secret_event, hpa_event]
        )
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        assert result.success is True
        types = {e["resource_type"] for e in result.data["change_events"]}
        assert "ConfigMap" in types
        assert "Secret" in types
        assert "HorizontalPodAutoscaler" in types

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_sorting_by_time_gap_ascending(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Correlations are sorted by time gap (closest first)."""
        now = datetime.now(timezone.utc)
        far_event = _make_k8s_event(
            kind="ConfigMap", name="old-config", timestamp=now - timedelta(minutes=40)
        )
        close_event = _make_k8s_event(
            kind="Secret", name="recent-secret", timestamp=now - timedelta(minutes=2)
        )

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(
            items=[far_event, close_event]
        )
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        events = result.data["change_events"]
        assert len(events) == 2
        assert events[0]["resource_name"] == "recent-secret"
        assert events[1]["resource_name"] == "old-config"
        assert events[0]["time_gap_seconds"] < events[1]["time_gap_seconds"]

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_deduplication_of_events_and_resource_modifications(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Duplicate events from K8s events and resource modifications are deduplicated."""
        now = datetime.now(timezone.utc)
        ts = now - timedelta(minutes=3)

        # K8s event for the ConfigMap
        event = _make_k8s_event(
            kind="ConfigMap",
            name="payments-config",
            timestamp=ts,
        )

        # Resource modification for the same ConfigMap at same time
        mock_cm = MagicMock()
        mock_cm.metadata.name = "payments-config"
        mock_field = MagicMock()
        mock_field.time = ts
        mock_cm.metadata.managed_fields = [mock_field]

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[event])
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[mock_cm])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        # Should be deduplicated — only 1 event, not 2
        assert len(result.data["change_events"]) == 1

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_filters_non_watched_resource_types(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Events for non-watched resource types are filtered out."""
        now = datetime.now(timezone.utc)
        pod_event = _make_k8s_event(
            kind="Pod",
            name="payments-abc123",
            timestamp=now - timedelta(minutes=3),
        )
        cm_event = _make_k8s_event(
            kind="ConfigMap",
            name="payments-config",
            timestamp=now - timedelta(minutes=3),
        )

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(
            items=[pod_event, cm_event]
        )
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step()
        result = step.execute()

        # Only ConfigMap event, Pod filtered out
        assert len(result.data["change_events"]) == 1
        assert result.data["change_events"][0]["resource_type"] == "ConfigMap"

    @patch("beeper_investigator.steps.change_event_correlation.client")
    @patch("beeper_investigator.steps.change_event_correlation.config")
    def test_uses_pipeline_metadata_anomaly_time(
        self, mock_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Uses anomaly_detected_at from pipeline_metadata if available."""
        now = datetime.now(timezone.utc)
        anomaly_time = now - timedelta(minutes=5)
        event = _make_k8s_event(
            kind="ConfigMap",
            name="payments-config",
            timestamp=now - timedelta(minutes=8),  # 3 min before anomaly
        )

        mock_core = MagicMock()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[event])
        mock_core.list_namespaced_config_map.return_value = MagicMock(items=[])
        mock_core.list_namespaced_secret.return_value = MagicMock(items=[])
        mock_client.CoreV1Api.return_value = mock_core

        mock_autoscaling = MagicMock()
        mock_autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            MagicMock(items=[])
        )
        mock_client.AutoscalingV1Api.return_value = mock_autoscaling

        mock_networking = MagicMock()
        mock_networking.list_namespaced_ingress.return_value = MagicMock(items=[])
        mock_client.NetworkingV1Api.return_value = mock_networking

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step(
            pipeline_metadata={"anomaly_detected_at": anomaly_time.isoformat()}
        )
        result = step.execute()

        assert result.success is True
        assert len(result.data["change_events"]) == 1
        # Time gap should be ~3 min (180 sec), not ~8 min
        gap = result.data["change_events"][0]["time_gap_seconds"]
        assert 170 <= gap <= 190  # Allow small timing variance


# ── TestFormatChangeSummary ──────────────────────────────────────────


class TestFormatChangeSummary:
    """Test change summary formatting."""

    def test_no_events_returns_fallback(self) -> None:
        step = _make_step()
        assert step._format_change_summary([]) == _NO_CHANGE_SUMMARY

    def test_summary_with_single_strong_event(self) -> None:
        step = _make_step()
        correlations = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "payments-config",
                "confidence": "strong",
                "time_gap_seconds": 180,
                "namespace": "default",
                "change_description": "Updated TIMEOUT_MS",
                "timestamp": "2026-03-18T14:30:00+00:00",
                "reason": "Modified",
            }
        ]
        summary = step._format_change_summary(correlations)
        assert "1 change event found" in summary
        assert "1 strong" in summary
        assert "ConfigMap payments-config" in summary
        assert "3 min" in summary

    def test_summary_with_mixed_confidence(self) -> None:
        step = _make_step()
        correlations = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "cm1",
                "confidence": "strong",
                "time_gap_seconds": 60,
                "namespace": "default",
                "change_description": "",
                "timestamp": "",
                "reason": "",
            },
            {
                "resource_type": "Secret",
                "resource_name": "s1",
                "confidence": "moderate",
                "time_gap_seconds": 600,
                "namespace": "default",
                "change_description": "",
                "timestamp": "",
                "reason": "",
            },
            {
                "resource_type": "Ingress",
                "resource_name": "i1",
                "confidence": "weak",
                "time_gap_seconds": 2400,
                "namespace": "default",
                "change_description": "",
                "timestamp": "",
                "reason": "",
            },
        ]
        summary = step._format_change_summary(correlations)
        assert "3 change events found" in summary
        assert "1 strong" in summary
        assert "1 moderate" in summary
        assert "1 weak" in summary
