"""Adaptive Alert Threshold Tuning service.

Evaluates investigation feedback per service to propose or auto-apply
alert threshold adjustments. Stores adjustment history for audit trail.

High "not-an-issue" feedback rate → raise thresholds (reduce sensitivity).
High "accurate" feedback rate → maintain or lower thresholds.
Trust-gated: TL1-2 = recommendation, TL3+ = auto-apply.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from beeper_ui.services.trust_level_service import TrustLevelService

logger = logging.getLogger(__name__)

ADJUSTMENTS_COLLECTION = "threshold_adjustments"
INVESTIGATIONS_COLLECTION = "investigations"
SERVICE_TRUST_COLLECTION = "service_trust_levels"

# Minimum feedback entries required before evaluation
MIN_FEEDBACK_SAMPLE = 10

# Default EWMA stddev multiplier baseline
DEFAULT_ALERT_THRESHOLD = 3.0

# Adjustment factors
RAISE_PCT = 0.15  # Raise threshold 15% for high false positive rate
LOWER_PCT = 0.10  # Lower threshold 10% for high accuracy rate
NOT_AN_ISSUE_HIGH_RATE = 0.5  # >=50% not-an-issue triggers raise
ACCURATE_HIGH_RATE = 0.7  # >=70% accurate triggers lower


@dataclass
class ThresholdAdjustment:
    """Record of a threshold adjustment with evidence."""

    adjustment_id: str
    service_name: str
    previous_threshold: float
    new_threshold: float
    adjustment_pct: float
    direction: str  # "increased" | "decreased" | "unchanged"
    status: str  # "applied" | "pending" | "rejected"
    reason: str  # human-readable explanation
    feedback_window: int  # total feedback entries evaluated
    not_an_issue_count: int
    accurate_count: int
    inaccurate_count: int
    trust_level: int
    created_at: str  # ISO 8601
    applied_at: str | None = None
    applied_by: str | None = None
    rejected_at: str | None = None
    rejected_by: str | None = None

    @classmethod
    def from_qdrant(cls, payload: dict[str, Any]) -> "ThresholdAdjustment":
        """Create ThresholdAdjustment from Qdrant point payload."""
        return cls(
            adjustment_id=payload.get("adjustment_id", ""),
            service_name=payload.get("service_name", ""),
            previous_threshold=payload.get("previous_threshold", DEFAULT_ALERT_THRESHOLD),
            new_threshold=payload.get("new_threshold", DEFAULT_ALERT_THRESHOLD),
            adjustment_pct=payload.get("adjustment_pct", 0.0),
            direction=payload.get("direction", "unchanged"),
            status=payload.get("status", "pending"),
            reason=payload.get("reason", ""),
            feedback_window=payload.get("feedback_window", 0),
            not_an_issue_count=payload.get("not_an_issue_count", 0),
            accurate_count=payload.get("accurate_count", 0),
            inaccurate_count=payload.get("inaccurate_count", 0),
            trust_level=payload.get("trust_level", 1),
            created_at=payload.get("created_at", ""),
            applied_at=payload.get("applied_at"),
            applied_by=payload.get("applied_by"),
            rejected_at=payload.get("rejected_at"),
            rejected_by=payload.get("rejected_by"),
        )


class AdaptiveThresholdError(Exception):
    """Exception raised by adaptive threshold service operations."""


class AdaptiveThresholdService:
    """Manages adaptive alert threshold tuning based on investigation feedback.

    Reads feedback from the investigations Qdrant collection, computes
    threshold adjustments, stores history in the threshold_adjustments
    collection, and updates per-service thresholds in service_trust_levels.
    """

    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host
        self._port = port
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        return self._client

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def get_service_feedback_summary(self, service_name: str) -> dict[str, int]:
        """Get feedback counts for a service from the investigations collection.

        Args:
            service_name: Name of the service to aggregate feedback for.

        Returns:
            Dict with keys: total, accurate, inaccurate, not_an_issue.

        Raises:
            AdaptiveThresholdError: On Qdrant communication failure.
        """
        summary: dict[str, int] = {
            "total": 0,
            "accurate": 0,
            "inaccurate": 0,
            "not_an_issue": 0,
        }

        try:
            offset = None
            while True:
                results, offset = self.client.scroll(
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
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in results:
                    payload = point.payload or {}
                    feedback = payload.get("investigation_feedback")
                    if feedback and feedback in summary:
                        summary[feedback] += 1
                        summary["total"] += 1

                if offset is None:
                    break

            return summary
        except Exception as e:
            msg = f"Failed to get feedback summary for {service_name}: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e

    def get_current_threshold(self, service_name: str) -> float:
        """Get current alert threshold for a service.

        Reads from the service_trust_levels collection's alert_threshold
        field, defaulting to DEFAULT_ALERT_THRESHOLD if not set.

        Args:
            service_name: Name of the service.

        Returns:
            Current threshold value (float).

        Raises:
            AdaptiveThresholdError: On Qdrant communication failure.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service_name",
                            match=MatchValue(value=service_name),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return DEFAULT_ALERT_THRESHOLD
            payload = results[0].payload or {}
            raw = payload.get("alert_threshold", DEFAULT_ALERT_THRESHOLD)
            # Boolean bypass guard — isinstance(True, (int, float)) is True
            if isinstance(raw, bool):
                return DEFAULT_ALERT_THRESHOLD
            return float(raw)
        except Exception as e:
            msg = f"Failed to get current threshold for {service_name}: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e

    @staticmethod
    def calculate_threshold_adjustment(
        service_name: str,
        current_threshold: float,
        feedback_summary: dict[str, int],
    ) -> ThresholdAdjustment | None:
        """Calculate threshold adjustment based on feedback.

        Pure calculation — no Qdrant access. Returns None if insufficient
        data or no adjustment is warranted.

        Args:
            service_name: Service name.
            current_threshold: Current EWMA stddev multiplier.
            feedback_summary: Dict with total, accurate, inaccurate, not_an_issue counts.

        Returns:
            ThresholdAdjustment if adjustment is warranted, None otherwise.
        """
        total = feedback_summary.get("total", 0)
        if total < MIN_FEEDBACK_SAMPLE:
            return None

        not_an_issue_count = feedback_summary.get("not_an_issue", 0)
        accurate_count = feedback_summary.get("accurate", 0)
        inaccurate_count = feedback_summary.get("inaccurate", 0)

        not_an_issue_rate = not_an_issue_count / total
        accurate_rate = accurate_count / total

        now = datetime.now(timezone.utc).isoformat()

        if not_an_issue_rate >= NOT_AN_ISSUE_HIGH_RATE:
            new_threshold = round(current_threshold * (1 + RAISE_PCT), 2)
            reason = (
                f"Raised threshold {RAISE_PCT * 100:.0f}%: "
                f"{not_an_issue_count}/{total} recent alerts marked not-an-issue"
            )
            return ThresholdAdjustment(
                adjustment_id=str(uuid.uuid4()),
                service_name=service_name,
                previous_threshold=current_threshold,
                new_threshold=new_threshold,
                adjustment_pct=round(RAISE_PCT * 100, 1),
                direction="increased",
                status="pending",  # Will be set by evaluate_service
                reason=reason,
                feedback_window=total,
                not_an_issue_count=not_an_issue_count,
                accurate_count=accurate_count,
                inaccurate_count=inaccurate_count,
                trust_level=1,  # Will be set by evaluate_service
                created_at=now,
            )

        if accurate_rate >= ACCURATE_HIGH_RATE:
            new_threshold = round(current_threshold * (1 - LOWER_PCT), 2)
            reason = (
                f"Lowered threshold {LOWER_PCT * 100:.0f}%: "
                f"{accurate_count}/{total} recent alerts marked accurate"
            )
            return ThresholdAdjustment(
                adjustment_id=str(uuid.uuid4()),
                service_name=service_name,
                previous_threshold=current_threshold,
                new_threshold=new_threshold,
                adjustment_pct=round(LOWER_PCT * 100, 1),
                direction="decreased",
                status="pending",
                reason=reason,
                feedback_window=total,
                not_an_issue_count=not_an_issue_count,
                accurate_count=accurate_count,
                inaccurate_count=inaccurate_count,
                trust_level=1,
                created_at=now,
            )

        # Mixed feedback — no adjustment
        return None

    def _update_service_threshold(
        self, service_name: str, new_threshold: float
    ) -> None:
        """Update per-service alert threshold in service_trust_levels collection.

        Args:
            service_name: Service to update.
            new_threshold: New threshold value.
        """
        now = datetime.now(timezone.utc).isoformat()
        results, _ = self.client.scroll(
            collection_name=SERVICE_TRUST_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="service_name",
                        match=MatchValue(value=service_name),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        if results:
            point_id = results[0].id
            payload = dict(results[0].payload or {})
        else:
            point_id = str(uuid.uuid4())
            payload = {"service_name": service_name}

        payload["alert_threshold"] = new_threshold
        payload["alert_threshold_updated_at"] = now

        self.client.upsert(
            collection_name=SERVICE_TRUST_COLLECTION,
            points=[PointStruct(id=point_id, vector=[0.0], payload=payload)],
        )

    def _store_adjustment(self, adjustment: ThresholdAdjustment) -> None:
        """Store a threshold adjustment record in the adjustments collection.

        Args:
            adjustment: The adjustment record to persist.
        """
        payload: dict[str, Any] = {
            "adjustment_id": adjustment.adjustment_id,
            "service_name": adjustment.service_name,
            "previous_threshold": adjustment.previous_threshold,
            "new_threshold": adjustment.new_threshold,
            "adjustment_pct": adjustment.adjustment_pct,
            "direction": adjustment.direction,
            "status": adjustment.status,
            "reason": adjustment.reason,
            "feedback_window": adjustment.feedback_window,
            "not_an_issue_count": adjustment.not_an_issue_count,
            "accurate_count": adjustment.accurate_count,
            "inaccurate_count": adjustment.inaccurate_count,
            "trust_level": adjustment.trust_level,
            "created_at": adjustment.created_at,
            "applied_at": adjustment.applied_at,
            "applied_by": adjustment.applied_by,
            "rejected_at": adjustment.rejected_at,
            "rejected_by": adjustment.rejected_by,
        }
        self.client.upsert(
            collection_name=ADJUSTMENTS_COLLECTION,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=[0.0],
                    payload=payload,
                )
            ],
        )

    def evaluate_service(
        self, service_name: str
    ) -> ThresholdAdjustment | None:
        """Evaluate feedback and propose/apply threshold adjustment.

        Reads feedback from investigations collection, computes adjustment,
        checks trust level, and either auto-applies (TL3+) or stores as
        pending recommendation (TL1-2).

        Args:
            service_name: Service to evaluate.

        Returns:
            ThresholdAdjustment if adjustment warranted, None otherwise.

        Raises:
            AdaptiveThresholdError: On Qdrant communication failure.
        """
        try:
            feedback = self.get_service_feedback_summary(service_name)
            current_threshold = self.get_current_threshold(service_name)

            adjustment = self.calculate_threshold_adjustment(
                service_name, current_threshold, feedback
            )
            if adjustment is None:
                return None

            # Get trust level for gating
            trust_svc = TrustLevelService(host=self._host, port=self._port)
            try:
                trust_level = trust_svc.get_effective_trust_level(service_name)
            finally:
                trust_svc.close()

            adjustment.trust_level = trust_level
            now = datetime.now(timezone.utc).isoformat()

            if trust_level >= 3:
                adjustment.status = "applied"
                adjustment.applied_at = now
                adjustment.applied_by = "system"
                self._update_service_threshold(
                    service_name, adjustment.new_threshold
                )
            else:
                adjustment.status = "pending"

            self._store_adjustment(adjustment)
            return adjustment
        except AdaptiveThresholdError:
            raise
        except Exception as e:
            msg = f"Failed to evaluate service {service_name}: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e

    def get_adjustment_history(
        self, service_name: str | None = None
    ) -> list[ThresholdAdjustment]:
        """Get threshold adjustment history.

        Args:
            service_name: Optional filter by service. None returns all.

        Returns:
            List of ThresholdAdjustment records sorted by created_at desc.

        Raises:
            AdaptiveThresholdError: On Qdrant communication failure.
        """
        try:
            scroll_filter = None
            if service_name:
                scroll_filter = Filter(
                    must=[
                        FieldCondition(
                            key="service_name",
                            match=MatchValue(value=service_name),
                        )
                    ]
                )

            adjustments: list[ThresholdAdjustment] = []
            offset = None
            while True:
                results, offset = self.client.scroll(
                    collection_name=ADJUSTMENTS_COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in results:
                    payload = point.payload or {}
                    adjustments.append(ThresholdAdjustment.from_qdrant(payload))

                if offset is None:
                    break

            # Sort by created_at descending
            adjustments.sort(key=lambda a: a.created_at, reverse=True)
            return adjustments
        except Exception as e:
            msg = f"Failed to get adjustment history: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e

    def apply_pending_adjustment(
        self, adjustment_id: str, applied_by: str
    ) -> ThresholdAdjustment:
        """Apply a pending threshold adjustment.

        Args:
            adjustment_id: ID of the pending adjustment.
            applied_by: User identity applying the adjustment.

        Returns:
            Updated ThresholdAdjustment with "applied" status.

        Raises:
            AdaptiveThresholdError: If adjustment not found or not pending.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=ADJUSTMENTS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="adjustment_id",
                            match=MatchValue(value=adjustment_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                raise AdaptiveThresholdError(
                    f"Adjustment {adjustment_id} not found"
                )

            point = results[0]
            payload = dict(point.payload or {})

            if payload.get("status") != "pending":
                raise AdaptiveThresholdError(
                    f"Adjustment {adjustment_id} is not pending "
                    f"(status: {payload.get('status')})"
                )

            # Apply the threshold change FIRST — if this fails, the
            # adjustment record still shows "pending" (consistent state).
            self._update_service_threshold(
                payload["service_name"], payload["new_threshold"]
            )

            # Only mark as "applied" after threshold is successfully updated
            now = datetime.now(timezone.utc).isoformat()
            payload["status"] = "applied"
            payload["applied_at"] = now
            payload["applied_by"] = applied_by

            self.client.upsert(
                collection_name=ADJUSTMENTS_COLLECTION,
                points=[
                    PointStruct(id=point.id, vector=[0.0], payload=payload)
                ],
            )

            return ThresholdAdjustment.from_qdrant(payload)
        except AdaptiveThresholdError:
            raise
        except Exception as e:
            msg = f"Failed to apply adjustment {adjustment_id}: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e

    def reject_pending_adjustment(
        self, adjustment_id: str, rejected_by: str
    ) -> ThresholdAdjustment:
        """Reject a pending threshold adjustment.

        Args:
            adjustment_id: ID of the pending adjustment.
            rejected_by: User identity rejecting the adjustment.

        Returns:
            Updated ThresholdAdjustment with "rejected" status.

        Raises:
            AdaptiveThresholdError: If adjustment not found or not pending.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=ADJUSTMENTS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="adjustment_id",
                            match=MatchValue(value=adjustment_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                raise AdaptiveThresholdError(
                    f"Adjustment {adjustment_id} not found"
                )

            point = results[0]
            payload = dict(point.payload or {})

            if payload.get("status") != "pending":
                raise AdaptiveThresholdError(
                    f"Adjustment {adjustment_id} is not pending "
                    f"(status: {payload.get('status')})"
                )

            now = datetime.now(timezone.utc).isoformat()
            payload["status"] = "rejected"
            payload["rejected_at"] = now
            payload["rejected_by"] = rejected_by

            self.client.upsert(
                collection_name=ADJUSTMENTS_COLLECTION,
                points=[
                    PointStruct(id=point.id, vector=[0.0], payload=payload)
                ],
            )

            return ThresholdAdjustment.from_qdrant(payload)
        except AdaptiveThresholdError:
            raise
        except Exception as e:
            msg = f"Failed to reject adjustment {adjustment_id}: {e}"
            logger.warning(msg)
            raise AdaptiveThresholdError(msg) from e
