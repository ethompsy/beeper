#!/usr/bin/env python3
"""Beeper UI demo with mocked backend services.

Runs the full Flask UI with realistic demo data, no infrastructure required.
Patches InvestigationService and KBService to return mock investigation data
that matches the investigator pipeline output.

Usage:
    python demo_ui.py
    # Then open http://localhost:5050/investigations/
"""

from datetime import datetime, timedelta, timezone

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationDetail,
    InvestigationService,
)

# ── Demo data ────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)
STARTED = (NOW - timedelta(minutes=12)).isoformat()
COMPLETED = (NOW - timedelta(minutes=7)).isoformat()
TRIGGERED = (NOW - timedelta(minutes=15)).isoformat()

DEMO_INVESTIGATIONS = [
    Investigation(
        id="inv-2026-087",
        status="completed",
        service="payments",
        severity="critical",
        condition="High error rate on /checkout endpoint — 5xx at 18%",
        started_at=STARTED,
        completed_at=COMPLETED,
        triggered_at=TRIGGERED,
    ),
    Investigation(
        id="inv-2026-086",
        status="investigating",
        service="auth-service",
        severity="high",
        condition="Elevated latency on /oauth/token — p99 > 5s",
        started_at=(NOW - timedelta(minutes=3)).isoformat(),
        triggered_at=(NOW - timedelta(minutes=5)).isoformat(),
    ),
    Investigation(
        id="inv-2026-085",
        status="completed",
        service="catalog",
        severity="medium",
        condition="Memory usage above 90% on catalog pods",
        started_at=(NOW - timedelta(hours=2)).isoformat(),
        completed_at=(NOW - timedelta(hours=1, minutes=45)).isoformat(),
        triggered_at=(NOW - timedelta(hours=2, minutes=5)).isoformat(),
    ),
    Investigation(
        id="inv-2026-084",
        status="completed",
        service="notifications",
        severity="low",
        condition="Increased queue depth on email-worker",
        started_at=(NOW - timedelta(days=1)).isoformat(),
        completed_at=(NOW - timedelta(days=1) + timedelta(minutes=20)).isoformat(),
        triggered_at=(NOW - timedelta(days=1)).isoformat(),
    ),
]

DEMO_DETAILS = {
    "inv-2026-087": InvestigationDetail(
        id="inv-2026-087",
        status="completed",
        service="payments",
        severity="critical",
        condition="High error rate on /checkout endpoint — 5xx at 18%",
        started_at=STARTED,
        completed_at=COMPLETED,
        triggered_at=TRIGGERED,
        message="Investigation complete",
        job_name="investigator-inv-2026-087",
    ),
    "inv-2026-086": InvestigationDetail(
        id="inv-2026-086",
        status="investigating",
        service="auth-service",
        severity="high",
        condition="Elevated latency on /oauth/token — p99 > 5s",
        started_at=(NOW - timedelta(minutes=3)).isoformat(),
        triggered_at=(NOW - timedelta(minutes=5)).isoformat(),
        message="Correlating signals across architectural layers",
        job_name="investigator-inv-2026-086",
    ),
    "inv-2026-085": InvestigationDetail(
        id="inv-2026-085",
        status="completed",
        service="catalog",
        severity="medium",
        condition="Memory usage above 90% on catalog pods",
        started_at=(NOW - timedelta(hours=2)).isoformat(),
        completed_at=(NOW - timedelta(hours=1, minutes=45)).isoformat(),
        triggered_at=(NOW - timedelta(hours=2, minutes=5)).isoformat(),
        message="Investigation complete",
        job_name="investigator-inv-2026-085",
    ),
    "inv-2026-084": InvestigationDetail(
        id="inv-2026-084",
        status="completed",
        service="notifications",
        severity="low",
        condition="Increased queue depth on email-worker",
        started_at=(NOW - timedelta(days=1)).isoformat(),
        completed_at=(NOW - timedelta(days=1) + timedelta(minutes=20)).isoformat(),
        triggered_at=(NOW - timedelta(days=1)).isoformat(),
        message="Investigation complete",
        job_name="investigator-inv-2026-084",
    ),
}

DEMO_FINDINGS = {
    "inv-2026-087": {
        "investigation_id": "inv-2026-087",
        "service": "payments",
        "condition": "High error rate on /checkout endpoint — 5xx at 18%",
        "severity": "critical",
        "status": "resolved",
        "customer_impacting": True,
        "reasoning": (
            "The /checkout endpoint is customer-facing; HTTP 5xx errors "
            "directly prevent users from completing purchases."
        ),
        "impact_model_tier": "screening",
        "impact_model_used": "claude-3-haiku-20240307",
        "kb_available": True,
        "prior_investigations_count": 1,
        "exact_match_found": True,
        "exact_match_id": "inv-2024-042",
        "prior_research_summary": (
            "Prior incident inv-2024-042 shows identical pattern: "
            "PgBouncer pool exhaustion caused checkout 5xx errors. "
            "Resolution was increasing pool limits."
        ),
        "recommended_resolution": (
            "Increase PgBouncer max_client_conn and default_pool_size"
        ),
        "confidence_boost": "high",
        "root_cause_hypothesis": (
            "PostgreSQL connection pool exhaustion on payments-db caused "
            "cascading query timeouts, leading to 5xx responses on /checkout"
        ),
        "confidence_level": "high",
        "confidence_percentage": 92,
        "supporting_evidence": [
            "pg_stat_activity at max_connections (100/100) for 12 min",
            "HTTP 5xx rate spiked from 0.1% to 18% at 14:32 UTC",
            "Prior incident inv-2024-042 confirms identical failure pattern",
            "Connection wait time p99 exceeded 30s (normal: <50ms)",
        ],
        "alternative_hypotheses": [],
        "additional_data_needs": [],
        "kb_citation": "inv-2024-042",
        "synthesis_source": "llm",
        "rca_model_tier": "deep_rca",
        "rca_model_used": "claude-opus-4",
        "recommendations": [
            {
                "action": (
                    "Increase PgBouncer max_client_conn from 100 to 200 "
                    "and default_pool_size from 20 to 40"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Immediate relief of connection pool saturation; "
                    "5xx rate drops to baseline within 2-3 min"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": "inv-2024-042",
            },
            {
                "action": (
                    "Add circuit breaker to payments-service DB adapter "
                    "with 50% error threshold and 30s recovery window"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Prevent cascading failures; degrade gracefully "
                    "instead of hard-failing all requests"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            },
            {
                "action": (
                    "Scale payments-service deployment from 3 to 6 replicas "
                    "to distribute connection load"
                ),
                "confidence": "medium",
                "expected_outcome": "Reduce per-pod connection pressure by ~50%",
                "risk_assessment": "medium",
                "based_on_prior_incident": None,
            },
        ],
        "ranking_rationale": (
            "PgBouncer config change is proven fix from prior incident "
            "inv-2024-042; circuit breaker is preventative with no downside; "
            "scaling is complementary but addresses symptom not root cause"
        ),
        "diagnostic_actions": [
            "Verify current pg_stat_activity with: SELECT count(*) FROM pg_stat_activity",
            "Check PgBouncer stats: SHOW POOLS",
        ],
        "resolution_model_tier": "standard",
        "resolution_model_used": "claude-sonnet-4",
        "model_usage": {
            "claude-3-haiku-20240307": 1,
            "claude-opus-4": 1,
            "claude-sonnet-4": 3,
        },
    },
    "inv-2026-086": {
        "investigation_id": "inv-2026-086",
        "service": "auth-service",
        "condition": "Elevated latency on /oauth/token — p99 > 5s",
        "severity": "high",
        "status": "investigating",
        "customer_impacting": True,
        "reasoning": (
            "The /oauth/token endpoint is used by all client apps for authentication; "
            "elevated latency causes login timeouts and degraded user experience."
        ),
        "impact_model_tier": "screening",
        "impact_model_used": "claude-3-haiku-20240307",
        "kb_available": True,
        "prior_investigations_count": 0,
        "exact_match_found": False,
        "prior_research_summary": "",
    },
    "inv-2026-085": {
        "investigation_id": "inv-2026-085",
        "service": "catalog",
        "condition": "Memory usage above 90% on catalog pods",
        "severity": "medium",
        "status": "resolved",
        "customer_impacting": False,
        "reasoning": (
            "High memory usage on catalog pods is an infrastructure concern "
            "but does not directly affect customer-facing functionality."
        ),
        "root_cause_hypothesis": (
            "In-memory cache growth without TTL eviction causing pod memory pressure"
        ),
        "confidence_level": "medium",
        "confidence_percentage": 65,
        "supporting_evidence": [
            "Pod memory at 92% (limit: 2Gi) across all 4 replicas",
            "Cache size growing linearly since last restart 3 days ago",
        ],
        "recommendations": [
            {
                "action": "Add TTL-based eviction to catalog cache (30min TTL recommended)",
                "confidence": "high",
                "expected_outcome": "Memory usage stabilizes at ~60%",
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            },
        ],
    },
    "inv-2026-084": {
        "investigation_id": "inv-2026-084",
        "service": "notifications",
        "condition": "Increased queue depth on email-worker",
        "severity": "low",
        "status": "resolved",
        "customer_impacting": False,
        "reasoning": "Email notifications are non-critical and eventually consistent.",
        "root_cause_hypothesis": (
            "SMTP relay rate limiting triggered by marketing campaign blast"
        ),
        "confidence_level": "high",
        "confidence_percentage": 88,
        "recommendations": [
            {
                "action": "Increase SMTP relay rate limit from 100/min to 500/min",
                "confidence": "high",
                "expected_outcome": "Queue drains within 10 minutes",
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            },
        ],
    },
}


# ── Monkey-patch services ────────────────────────────────────────────────────


def _mock_list_investigations(self, status=None, service=None, severity=None):
    results = list(DEMO_INVESTIGATIONS)
    if status:
        results = [i for i in results if i.status == status]
    if service:
        results = [i for i in results if i.service == service]
    if severity:
        results = [i for i in results if i.severity == severity]
    return results


def _mock_get_investigation(self, investigation_id):
    return DEMO_DETAILS.get(investigation_id)


def _mock_get_findings(self, investigation_id):
    return dict(DEMO_FINDINGS.get(investigation_id, {}))


def _mock_confirm(self, investigation_id, comment=None):
    return investigation_id in DEMO_DETAILS


def _mock_reject(self, investigation_id, reason="", reason_details=None, correction=None):
    return investigation_id in DEMO_DETAILS


def _mock_resolve(self, investigation_id, outcome="resolved", **kwargs):
    return investigation_id in DEMO_DETAILS


def _mock_save_feedback(self, investigation_id, feedback):
    pass


def _mock_update_kb(self, investigation_id, resolution_data):
    return False


def _mock_close(self):
    pass


# Patch InvestigationService
InvestigationService.list_investigations = _mock_list_investigations
InvestigationService.get_investigation = _mock_get_investigation
InvestigationService.get_investigation_findings = _mock_get_findings
InvestigationService.confirm_resolution = _mock_confirm
InvestigationService.reject_resolution = _mock_reject
InvestigationService.resolve_investigation = _mock_resolve
InvestigationService.save_resolution_feedback = _mock_save_feedback
InvestigationService.update_kb_with_resolution = _mock_update_kb
InvestigationService.close = _mock_close

# Patch KBService to avoid Qdrant connections
from beeper_ui.services.kb_service import KBService

KBService.list_entries_by_service = lambda self, *a, **kw: []
KBService.get_entry = lambda self, *a, **kw: None
KBService.close = lambda self: None

# Patch SSE generators to not repeat events.
# The real SSE generators close the connection after sending a completion event,
# which causes HTMX to auto-reconnect, creating an infinite loop of duplicate
# updates. For the demo, we replace them with idle generators that keep the
# connection alive without sending any events (the initial page render already
# includes all data via template includes).
import time as _time
from collections.abc import Generator as _Generator

import beeper_ui.routes.investigations as _inv_routes


def _idle_detail_sse(
    operator_url: str,
    operator_timeout: float,
    investigation_id: str,
) -> _Generator[str, None, None]:
    """SSE generator that keeps connection open without sending events."""
    while True:
        try:
            _time.sleep(30)
            # Send keepalive comment (SSE spec: lines starting with ':' are ignored)
            yield ": keepalive\n\n"
        except GeneratorExit:
            return


def _idle_list_sse(
    operator_url: str, operator_timeout: float
) -> _Generator[str, None, None]:
    """SSE generator that keeps connection open without sending events."""
    while True:
        try:
            _time.sleep(30)
            yield ": keepalive\n\n"
        except GeneratorExit:
            return


_inv_routes._generate_detail_sse_events = _idle_detail_sse
_inv_routes._generate_sse_events = _idle_list_sse


# ── Start the app ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from beeper_ui.app import create_app
    from beeper_ui.config import DevelopmentConfig

    app = create_app(DevelopmentConfig)

    print("\n\033[1m\033[34m" + "=" * 60)
    print("  BEEPER UI DEMO")
    print("=" * 60 + "\033[0m\n")
    print("  Open in your browser:")
    print("  \033[1mhttp://localhost:5050/investigations/\033[0m\n")
    print("  Demo investigations:")
    for inv in DEMO_INVESTIGATIONS:
        sev_color = {"critical": "31", "high": "33", "medium": "36", "low": "32"}
        color = sev_color.get(inv.severity, "0")
        print(f"    \033[{color}m[{inv.severity:>8}]\033[0m {inv.id} — {inv.condition[:50]}")
    print(f"\n  \033[2mClick any investigation to see full details.\033[0m\n")

    app.run(debug=True, host="127.0.0.1", port=5050)
