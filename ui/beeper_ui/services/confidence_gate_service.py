"""Confidence Gate service for evaluating action eligibility.

This module implements the confidence gate engine that determines whether
an investigation's confidence score is sufficient for autonomous action
at a service's configured trust level (TL1-5).

Trust levels TL1-2 are always advisory (no gate evaluation needed).
Trust levels TL3-5 gate by confidence threshold:
  TL3: 0.90 (90%) default
  TL4: 0.85 (85%) default
  TL5: 0.80 (80%) default

Actions below threshold fall back to advisory-only behavior.
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

from beeper_ui.services.trust_level_service import (
    TRUST_LEVEL_DEFINITIONS,
    TrustLevelService,
    TrustLevelServiceError,
)

logger = logging.getLogger(__name__)

# Reuse existing collection — gate threshold fields use "gate_" prefix
SERVICE_TRUST_COLLECTION = "service_trust_levels"

# Sentinel key for gate threshold configuration record
GATE_THRESHOLDS_KEY = "__gate_thresholds__"

# Default confidence gate thresholds per trust level
# TL1-2 have no thresholds (always advisory)
DEFAULT_GATE_THRESHOLDS: dict[int, float] = {
    3: 0.90,
    4: 0.85,
    5: 0.80,
}

# Trust levels that support confidence gating
GATED_TRUST_LEVELS = {3, 4, 5}

# Min/max trust levels for gate configuration
MIN_GATED_LEVEL = 3
MAX_GATED_LEVEL = 5

# Confidence score text-to-numeric mapping
TEXT_CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.85,
    "medium": 0.65,
    "low": 0.35,
}

# Composite confidence score weights
COMPOSITE_WEIGHTS: dict[str, float] = {
    "rca": 0.5,
    "signal_correlation": 0.3,
    "kb_match": 0.2,
}


@dataclass
class GateDecision:
    """Result of confidence gate evaluation."""

    permitted: bool
    confidence_score: float
    threshold: float
    trust_level: int
    action_type: str  # "autonomous" or "advisory"
    reason: str
    service_name: str


@dataclass
class ConfidenceGateConfig:
    """Confidence gate threshold configuration for a trust level."""

    trust_level: int  # 3, 4, or 5
    threshold: float  # 0.0-1.0
    updated_by: str
    updated_at: str  # ISO 8601
    description: str  # Trust level name

    @classmethod
    def from_qdrant(
        cls, trust_level: int, payload: dict[str, Any]
    ) -> "ConfidenceGateConfig":
        """Create ConfidenceGateConfig from Qdrant payload."""
        defn = TRUST_LEVEL_DEFINITIONS.get(trust_level, {})
        threshold_key = f"gate_threshold_tl{trust_level}"
        return cls(
            trust_level=trust_level,
            threshold=payload.get(
                threshold_key, DEFAULT_GATE_THRESHOLDS.get(trust_level, 0.90)
            ),
            updated_by=payload.get("gate_updated_by", ""),
            updated_at=payload.get("gate_updated_at", ""),
            description=defn.get("name", "Unknown"),
        )


class ConfidenceGateError(Exception):
    """Exception raised by confidence gate operations."""


def normalize_confidence_score(investigation_findings: dict[str, Any]) -> float:
    """Normalize investigator confidence data to a 0.0-1.0 score.

    Handles mixed formats from the investigation pipeline:
    - RCA: confidence_percentage (0-100) or confidence_level (text)
    - Signal correlation: confidence (text)
    - KB query: confidence_boost (text)

    Returns composite weighted score, or single source if only one available.
    Missing data defaults to 0.0 (safest — always advisory).
    """
    scores: dict[str, float] = {}

    # RCA confidence (weight 0.5)
    rca_data = investigation_findings.get("rca_hypothesis") or {}
    if isinstance(rca_data, dict):
        rca_pct = rca_data.get("confidence_percentage")
        if isinstance(rca_pct, (int, float)) and not isinstance(rca_pct, bool):
            scores["rca"] = max(0.0, min(1.0, rca_pct / 100.0))
        else:
            rca_text = rca_data.get("confidence_level", "")
            if isinstance(rca_text, str) and rca_text.lower() in TEXT_CONFIDENCE_MAP:
                scores["rca"] = TEXT_CONFIDENCE_MAP[rca_text.lower()]

    # Signal correlation confidence (weight 0.3)
    hypotheses = investigation_findings.get("hypotheses") or []
    if isinstance(hypotheses, list) and hypotheses:
        # Use highest confidence hypothesis
        best_confidence = 0.0
        for h in hypotheses:
            if isinstance(h, dict):
                conf_text = h.get("confidence", "")
                if (
                    isinstance(conf_text, str)
                    and conf_text.lower() in TEXT_CONFIDENCE_MAP
                ):
                    best_confidence = max(
                        best_confidence, TEXT_CONFIDENCE_MAP[conf_text.lower()]
                    )
        if best_confidence > 0.0:
            scores["signal_correlation"] = best_confidence

    # KB match confidence (weight 0.2)
    kb_boost = investigation_findings.get("confidence_boost")
    if isinstance(kb_boost, str) and kb_boost.lower() in TEXT_CONFIDENCE_MAP:
        scores["kb_match"] = TEXT_CONFIDENCE_MAP[kb_boost.lower()]

    if not scores:
        return 0.0

    # If only one source, use it directly
    if len(scores) == 1:
        return next(iter(scores.values()))

    # Composite weighted average using available weights
    total_weight = sum(
        COMPOSITE_WEIGHTS[key] for key in scores if key in COMPOSITE_WEIGHTS
    )
    if total_weight == 0.0:
        return 0.0

    weighted_sum = sum(
        scores[key] * COMPOSITE_WEIGHTS[key]
        for key in scores
        if key in COMPOSITE_WEIGHTS
    )
    return weighted_sum / total_weight


def format_gate_message(decision: GateDecision) -> str:
    """Format a GateDecision as a human-readable message.

    Examples:
        "Confidence: 95% — meets threshold (90%) for autonomous action"
        "Confidence: 80% — below threshold (85%) for auto-action — advisory only"
        "Trust level 1 is advisory-only — no autonomous actions permitted"
    """
    score_pct = int(round(decision.confidence_score * 100))
    threshold_pct = int(round(decision.threshold * 100))

    if decision.trust_level <= 2:
        tl_name = TRUST_LEVEL_DEFINITIONS.get(decision.trust_level, {}).get(
            "name", "Advisory"
        )
        return (
            f"Trust level {decision.trust_level} ({tl_name}) is advisory-only"
            f" \u2014 no autonomous actions permitted"
        )

    if decision.permitted:
        return (
            f"Confidence: {score_pct}% \u2014 meets threshold"
            f" ({threshold_pct}%) for autonomous action"
        )

    return (
        f"Confidence: {score_pct}% \u2014 below threshold"
        f" ({threshold_pct}%) for auto-action \u2014 advisory only"
    )


class ConfidenceGateService:
    """Evaluates confidence gates for investigation actions.

    Uses TrustLevelService for trust level lookups and stores
    gate threshold configuration in the service_trust_levels
    Qdrant collection.
    """

    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host
        self._port = port
        self._client: QdrantClient | None = None
        self._trust_service: TrustLevelService | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        return self._client

    @property
    def trust_service(self) -> TrustLevelService:
        """Lazy-initialize TrustLevelService."""
        if self._trust_service is None:
            self._trust_service = TrustLevelService(
                host=self._host, port=self._port
            )
        return self._trust_service

    def close(self) -> None:
        """Close connections."""
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._trust_service is not None:
            self._trust_service.close()
            self._trust_service = None

    def evaluate_gate(
        self,
        service_name: str,
        confidence_score: float,
        action_context: str | None = None,
    ) -> GateDecision:
        """Evaluate whether an action passes the confidence gate.

        Args:
            service_name: Name of the service.
            confidence_score: Normalized confidence score (0.0-1.0).
            action_context: Optional description of the proposed action.

        Returns:
            GateDecision with permit/deny result and reasoning.
        """
        # Get effective trust level (defaults to TL1)
        try:
            trust_level = self.trust_service.get_effective_trust_level(
                service_name
            )
        except TrustLevelServiceError:
            trust_level = 1

        # TL1-2: Always advisory
        if trust_level not in GATED_TRUST_LEVELS:
            tl_name = TRUST_LEVEL_DEFINITIONS.get(trust_level, {}).get(
                "name", "Advisory"
            )
            return GateDecision(
                permitted=False,
                confidence_score=confidence_score,
                threshold=0.0,
                trust_level=trust_level,
                action_type="advisory",
                reason=(
                    f"Trust level {trust_level} ({tl_name}) is advisory-only"
                ),
                service_name=service_name,
            )

        # TL3-5: Evaluate against threshold
        try:
            gate_config = self.get_gate_threshold(trust_level)
            threshold = gate_config.threshold
        except ConfidenceGateError:
            threshold = DEFAULT_GATE_THRESHOLDS.get(trust_level, 0.90)

        permitted = confidence_score >= threshold

        return GateDecision(
            permitted=permitted,
            confidence_score=confidence_score,
            threshold=threshold,
            trust_level=trust_level,
            action_type="autonomous" if permitted else "advisory",
            reason=(
                f"Confidence {int(round(confidence_score * 100))}% "
                f"{'meets' if permitted else 'below'} threshold "
                f"{int(round(threshold * 100))}%"
            ),
            service_name=service_name,
        )

    def get_gate_thresholds(self) -> list[ConfidenceGateConfig]:
        """Get all gate threshold configurations (defaults + custom).

        Returns:
            List of ConfidenceGateConfig for TL3, TL4, TL5.
        """
        custom_payload = self._load_threshold_payload()

        configs = []
        for tl in sorted(GATED_TRUST_LEVELS):
            if custom_payload:
                configs.append(
                    ConfidenceGateConfig.from_qdrant(tl, custom_payload)
                )
            else:
                defn = TRUST_LEVEL_DEFINITIONS.get(tl, {})
                configs.append(
                    ConfidenceGateConfig(
                        trust_level=tl,
                        threshold=DEFAULT_GATE_THRESHOLDS[tl],
                        updated_by="",
                        updated_at="",
                        description=defn.get("name", "Unknown"),
                    )
                )
        return configs

    def get_gate_threshold(self, trust_level: int) -> ConfidenceGateConfig:
        """Get gate threshold for a specific trust level.

        Args:
            trust_level: Trust level (3-5).

        Returns:
            ConfidenceGateConfig for the requested level.

        Raises:
            ValueError: If trust_level is not 3-5.
            ConfidenceGateError: On Qdrant communication failure.
        """
        if trust_level not in GATED_TRUST_LEVELS:
            msg = (
                f"Confidence gates only apply to trust levels "
                f"{MIN_GATED_LEVEL}-{MAX_GATED_LEVEL}, got {trust_level}"
            )
            raise ValueError(msg)

        custom_payload = self._load_threshold_payload()
        if custom_payload:
            return ConfidenceGateConfig.from_qdrant(
                trust_level, custom_payload
            )

        defn = TRUST_LEVEL_DEFINITIONS.get(trust_level, {})
        return ConfidenceGateConfig(
            trust_level=trust_level,
            threshold=DEFAULT_GATE_THRESHOLDS[trust_level],
            updated_by="",
            updated_at="",
            description=defn.get("name", "Unknown"),
        )

    def set_gate_threshold(
        self,
        trust_level: int,
        threshold: float,
        updated_by: str,
    ) -> ConfidenceGateConfig:
        """Set or update gate threshold for a trust level.

        Args:
            trust_level: Trust level (3-5).
            threshold: Confidence threshold (0.0-1.0).
            updated_by: Identity of the user making the change.

        Returns:
            Updated ConfidenceGateConfig.

        Raises:
            ValueError: If trust_level not 3-5 or threshold not 0.0-1.0.
            ConfidenceGateError: On Qdrant communication failure.
        """
        if trust_level not in GATED_TRUST_LEVELS:
            msg = (
                f"Confidence gates only apply to trust levels "
                f"{MIN_GATED_LEVEL}-{MAX_GATED_LEVEL}, got {trust_level}"
            )
            raise ValueError(msg)

        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or threshold < 0.0
            or threshold > 1.0
        ):
            msg = f"Threshold must be a number between 0.0 and 1.0, got {threshold}"
            raise ValueError(msg)

        threshold = float(threshold)
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Load existing thresholds record or create new
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service_name",
                            match=MatchValue(value=GATE_THRESHOLDS_KEY),
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
                payload = {"service_name": GATE_THRESHOLDS_KEY}
                # Initialize all defaults
                for tl, default_thresh in DEFAULT_GATE_THRESHOLDS.items():
                    payload[f"gate_threshold_tl{tl}"] = default_thresh

            # Update the specific threshold
            payload[f"gate_threshold_tl{trust_level}"] = threshold
            payload["gate_updated_by"] = updated_by
            payload["gate_updated_at"] = now

            self.client.upsert(
                collection_name=SERVICE_TRUST_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=[0.0],
                        payload=payload,
                    )
                ],
            )

            defn = TRUST_LEVEL_DEFINITIONS.get(trust_level, {})
            return ConfidenceGateConfig(
                trust_level=trust_level,
                threshold=threshold,
                updated_by=updated_by,
                updated_at=now,
                description=defn.get("name", "Unknown"),
            )
        except Exception as e:
            msg = f"Failed to set gate threshold for TL{trust_level}: {e}"
            logger.warning(msg)
            raise ConfidenceGateError(msg) from e

    def _load_threshold_payload(self) -> dict[str, Any] | None:
        """Load custom gate threshold payload from Qdrant.

        Returns:
            Payload dict if custom thresholds exist, None otherwise.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service_name",
                            match=MatchValue(value=GATE_THRESHOLDS_KEY),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if results:
                return results[0].payload or {}
            return None
        except Exception as e:
            logger.warning("Failed to load gate thresholds: %s", e)
            return None
