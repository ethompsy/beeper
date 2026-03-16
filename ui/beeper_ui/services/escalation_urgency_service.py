"""Escalation Urgency service.

Computes impact-weighted urgency scores for investigations by combining
SLO data (burn rate, budget remaining) with investigation feedback accuracy.
Replaces static severity mapping with dynamic, evidence-based urgency.

Urgency = f(burn_rate, budget_remaining, severity, customer_impact, feedback_accuracy).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"

# Urgency weight factors (must sum to 1.0 when SLO data available)
BURN_RATE_WEIGHT = 0.40
BUDGET_WEIGHT = 0.35
SEVERITY_WEIGHT = 0.25

# Severity score mapping (0-100)
SEVERITY_SCORES: dict[str, float] = {
    "critical": 100.0,
    "high": 75.0,
    "medium": 50.0,
    "low": 25.0,
}

# Customer impact multiplier (applied when customer_impacting=True)
CUSTOMER_IMPACT_BOOST = 1.2

# Confidence dampening for low-accuracy services
LOW_CONFIDENCE_DAMPENING = 0.7

# Accuracy rate thresholds for confidence assessment
ACCURATE_HIGH_RATE = 0.8  # >=80% accurate → high confidence
ACCURATE_LOW_RATE = 0.5  # <50% accurate → low confidence, dampen

# Minimum feedback entries required for confidence assessment
MIN_FEEDBACK_FOR_CONFIDENCE = 10

# Burn rate normalization ceiling (5x is considered max urgency)
BURN_RATE_CEILING = 5.0


@dataclass
class UrgencyScore:
    """Impact-weighted escalation urgency score for an investigation."""

    score: float  # 0-100
    confidence: str  # "high" | "moderate" | "low" | "unknown"
    low_confidence: bool
    factors: dict[str, Any] = field(default_factory=dict)
    service_name: str = ""
    investigation_id: str = ""
    has_slo_data: bool = False

    @classmethod
    def default(cls) -> "UrgencyScore":
        """Return a default urgency score (no data available)."""
        return cls(
            score=0.0,
            confidence="unknown",
            low_confidence=False,
            factors={
                "burn_rate_component": 0.0,
                "budget_component": 0.0,
                "severity_component": 0.0,
                "customer_impact_boost": False,
                "confidence_dampening": False,
            },
            has_slo_data=False,
        )


class EscalationUrgencyError(Exception):
    """Error computing escalation urgency."""

    pass


class EscalationUrgencyService:
    """Computes impact-weighted escalation urgency scores.

    Combines SLO burn rate / budget data with investigation feedback
    accuracy to produce dynamic urgency scores that replace static
    severity mapping.
    """

    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host
        self._port = port
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Get or create the Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        return self._client

    def close(self) -> None:
        """Close the Qdrant client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def get_service_accuracy_rate(self, service_name: str) -> dict[str, Any]:
        """Get feedback accuracy rate for a service.

        Scrolls the investigations collection filtered by service name,
        aggregates investigation_feedback field values.

        Returns:
            Dict with accurate_rate (float|None), total_feedback (int),
            accurate_count, inaccurate_count, not_an_issue_count.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service",
                            match=MatchValue(value=service_name),
                        )
                    ]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            raise EscalationUrgencyError(
                f"Failed to fetch feedback for {service_name}: {e}"
            ) from e

        feedback_entries = [
            r
            for r in results
            if r.payload and r.payload.get("investigation_feedback")
        ]
        total = len(feedback_entries)
        accurate = sum(
            1
            for e in feedback_entries
            if e.payload["investigation_feedback"] == "accurate"
        )
        inaccurate = sum(
            1
            for e in feedback_entries
            if e.payload["investigation_feedback"] == "inaccurate"
        )
        not_an_issue = sum(
            1
            for e in feedback_entries
            if e.payload["investigation_feedback"] == "not_an_issue"
        )

        accurate_rate: float | None = None
        if total >= MIN_FEEDBACK_FOR_CONFIDENCE:
            accurate_rate = accurate / total

        return {
            "accurate_rate": accurate_rate,
            "total_feedback": total,
            "accurate_count": accurate,
            "inaccurate_count": inaccurate,
            "not_an_issue_count": not_an_issue,
        }

    def calculate_urgency(
        self,
        investigation_id: str,
        service_name: str,
        severity: str,
        burn_rate: float | None,
        budget_remaining: float | None,
        customer_impacting: bool,
        accuracy_data: dict[str, Any],
    ) -> UrgencyScore:
        """Calculate impact-weighted urgency score for an investigation.

        Args:
            investigation_id: Investigation ID.
            service_name: Service name.
            severity: Investigation severity (low/medium/high/critical).
            burn_rate: SLO burn rate multiplier, or None if no SLO.
            budget_remaining: SLO budget remaining (0.0-1.0), or None.
            customer_impacting: Whether investigation is customer-impacting.
            accuracy_data: Dict from get_service_accuracy_rate().

        Returns:
            UrgencyScore with composite score, confidence, and factors.
        """
        severity_score = SEVERITY_SCORES.get(severity, 50.0)
        burn_rate_score = 0.0
        budget_score = 0.0
        has_slo_data = False

        if burn_rate is not None and budget_remaining is not None:
            # Validate numeric types (guard against booleans)
            if isinstance(burn_rate, bool) or isinstance(budget_remaining, bool):
                # Fall back to severity-only
                base_urgency = severity_score
            else:
                has_slo_data = True
                burn_rate_score = (
                    min(float(burn_rate) / BURN_RATE_CEILING, 1.0) * 100.0
                )
                clamped_budget = max(0.0, min(1.0, float(budget_remaining)))
                budget_score = (1.0 - clamped_budget) * 100.0
                base_urgency = (
                    burn_rate_score * BURN_RATE_WEIGHT
                    + budget_score * BUDGET_WEIGHT
                    + severity_score * SEVERITY_WEIGHT
                )
        else:
            # Severity-only fallback when no SLO data
            base_urgency = severity_score

        # Customer impact boost
        customer_impact_applied = False
        if customer_impacting:
            base_urgency = min(base_urgency * CUSTOMER_IMPACT_BOOST, 100.0)
            customer_impact_applied = True

        # Confidence assessment and dampening (AC #2)
        accurate_rate = accuracy_data.get("accurate_rate")
        confidence_dampening_applied = False

        if accurate_rate is not None:
            if isinstance(accurate_rate, bool):
                confidence = "unknown"
            elif accurate_rate >= ACCURATE_HIGH_RATE:
                confidence = "high"
            elif accurate_rate < ACCURATE_LOW_RATE:
                confidence = "low"
                base_urgency *= LOW_CONFIDENCE_DAMPENING
                confidence_dampening_applied = True
            else:
                confidence = "moderate"
        else:
            confidence = "unknown"

        # Clamp final score to 0-100
        final_score = round(max(0.0, min(100.0, base_urgency)), 1)

        return UrgencyScore(
            score=final_score,
            confidence=confidence,
            low_confidence=(confidence == "low"),
            factors={
                "burn_rate_component": round(
                    burn_rate_score * BURN_RATE_WEIGHT, 1
                )
                if has_slo_data
                else 0.0,
                "budget_component": round(budget_score * BUDGET_WEIGHT, 1)
                if has_slo_data
                else 0.0,
                "severity_component": round(
                    severity_score * SEVERITY_WEIGHT, 1
                )
                if has_slo_data
                else severity_score,
                "customer_impact_boost": customer_impact_applied,
                "confidence_dampening": confidence_dampening_applied,
            },
            service_name=service_name,
            investigation_id=investigation_id,
            has_slo_data=has_slo_data,
        )

    def compute_batch_urgency(
        self,
        investigations: list[Any],
        slo_budgets: dict[str, dict[str, Any] | None],
        findings_map: dict[str, dict[str, Any]],
    ) -> dict[str, UrgencyScore]:
        """Compute urgency scores for a batch of investigations.

        Caches feedback accuracy per unique service to minimize Qdrant calls.

        Args:
            investigations: List of Investigation objects (need .id, .service, .severity).
            slo_budgets: Dict of service_name → SLO budget dict (or None).
            findings_map: Dict of investigation_id → findings payload dict.

        Returns:
            Dict of investigation_id → UrgencyScore.
        """
        # Cache accuracy data per service
        accuracy_cache: dict[str, dict[str, Any]] = {}
        urgency_scores: dict[str, UrgencyScore] = {}

        for inv in investigations:
            service = inv.service
            inv_id = inv.id

            # Get or compute accuracy data for this service
            if service not in accuracy_cache:
                try:
                    accuracy_cache[service] = self.get_service_accuracy_rate(
                        service
                    )
                except EscalationUrgencyError:
                    logger.warning(
                        "Failed to get accuracy for %s, using unknown",
                        service,
                    )
                    accuracy_cache[service] = {
                        "accurate_rate": None,
                        "total_feedback": 0,
                        "accurate_count": 0,
                        "inaccurate_count": 0,
                        "not_an_issue_count": 0,
                    }

            # Extract SLO data for this service
            budget = slo_budgets.get(service)
            burn_rate = None
            budget_remaining = None
            if budget:
                burn_rate = budget.get("burn_rate")
                budget_remaining = budget.get("budget_remaining")

            # Extract customer impact from findings
            findings = findings_map.get(inv_id, {})
            customer_impacting = bool(findings.get("customer_impacting", False))

            urgency_scores[inv_id] = self.calculate_urgency(
                investigation_id=inv_id,
                service_name=service,
                severity=inv.severity,
                burn_rate=burn_rate,
                budget_remaining=budget_remaining,
                customer_impacting=customer_impacting,
                accuracy_data=accuracy_cache[service],
            )

        return urgency_scores
