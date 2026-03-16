"""Trust Level service for per-service autonomy configuration.

This module provides CRUD operations for managing Beeper's per-service
trust levels (TL1-5), which control how autonomous Beeper can be when
handling investigations for each service.

NOTE: This is SEPARATE from the KB authoring trust in kb_service.py.
KB trust tracks "draft"/"trusted" for knowledge base entries.
Autonomy trust (this module) controls Beeper's operational autonomy (TL1-5).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

logger = logging.getLogger(__name__)

# Reuse existing collection — autonomy fields are prefixed with "autonomy_"
SERVICE_TRUST_COLLECTION = "service_trust_levels"

# Valid trust levels (1-5)
MIN_TRUST_LEVEL = 1
MAX_TRUST_LEVEL = 5
DEFAULT_TRUST_LEVEL = 1

TRUST_LEVEL_DEFINITIONS: dict[int, dict[str, str]] = {
    1: {
        "name": "Advisory Only",
        "description": "No autonomous actions; all outputs advisory.",
    },
    2: {
        "name": "Suggest with Evidence",
        "description": (
            "Suggest actions with supporting evidence; requires manual approval."
        ),
    },
    3: {
        "name": "Act with Approval",
        "description": (
            "Take actions after explicit SRE approval; gate by confidence threshold."
        ),
    },
    4: {
        "name": "Act and Notify",
        "description": (
            "Take actions autonomously; notify admin; gate by confidence threshold."
        ),
    },
    5: {
        "name": "Fully Autonomous",
        "description": "Full autonomy within configured scope.",
    },
}


@dataclass
class TrustLevelConfig:
    """Per-service autonomy trust level configuration."""

    service_name: str
    trust_level: int  # 1-5
    updated_by: str
    updated_at: str  # ISO 8601
    reason: str | None = None
    previous_level: int | None = None

    @classmethod
    def from_qdrant(cls, payload: dict[str, Any]) -> "TrustLevelConfig":
        """Create TrustLevelConfig from Qdrant point payload."""
        return cls(
            service_name=payload.get("service_name", ""),
            trust_level=payload.get("autonomy_level", DEFAULT_TRUST_LEVEL),
            updated_by=payload.get("autonomy_updated_by", ""),
            updated_at=payload.get("autonomy_updated_at", ""),
            reason=payload.get("autonomy_reason"),
            previous_level=payload.get("autonomy_previous_level"),
        )


class TrustLevelServiceError(Exception):
    """Exception raised by trust level service operations."""


class TrustLevelService:
    """Manages per-service autonomy trust levels (TL1-5) in Qdrant.

    Uses the existing service_trust_levels collection with autonomy_*
    prefixed fields to avoid conflicts with KB trust fields.
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

    def get_service_trust_level(
        self, service_name: str
    ) -> TrustLevelConfig | None:
        """Get autonomy trust level for a specific service.

        Args:
            service_name: Name of the service.

        Returns:
            TrustLevelConfig if found, None if no autonomy level configured.

        Raises:
            TrustLevelServiceError: On Qdrant communication failure.
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
                return None
            payload = results[0].payload or {}
            # Only return if autonomy level has been configured
            if "autonomy_level" not in payload:
                return None
            return TrustLevelConfig.from_qdrant(payload)
        except (UnexpectedResponse, Exception) as e:
            msg = f"Failed to get trust level for {service_name}: {e}"
            logger.warning(msg)
            raise TrustLevelServiceError(msg) from e

    def get_all_trust_levels(self) -> list[TrustLevelConfig]:
        """Get all configured autonomy trust levels.

        Returns:
            List of TrustLevelConfig for services with autonomy levels set.

        Raises:
            TrustLevelServiceError: On Qdrant communication failure.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                limit=200,
                with_payload=True,
                with_vectors=False,
            )
            configs = []
            for point in results:
                payload = point.payload or {}
                if "autonomy_level" in payload:
                    configs.append(TrustLevelConfig.from_qdrant(payload))
            return configs
        except (UnexpectedResponse, Exception) as e:
            msg = f"Failed to list trust levels: {e}"
            logger.warning(msg)
            raise TrustLevelServiceError(msg) from e

    def set_trust_level(
        self,
        service_name: str,
        level: int,
        updated_by: str,
        reason: str | None = None,
    ) -> TrustLevelConfig:
        """Set or update autonomy trust level for a service.

        Args:
            service_name: Name of the service.
            level: Trust level (1-5).
            updated_by: Identity of the user making the change.
            reason: Optional reason for the change.

        Returns:
            Updated TrustLevelConfig.

        Raises:
            ValueError: If level is not 1-5.
            TrustLevelServiceError: On Qdrant communication failure.
        """
        if not isinstance(level, int) or level < MIN_TRUST_LEVEL or level > MAX_TRUST_LEVEL:
            msg = (
                f"Trust level must be an integer between "
                f"{MIN_TRUST_LEVEL} and {MAX_TRUST_LEVEL}, got {level}"
            )
            raise ValueError(msg)

        now = datetime.now(timezone.utc).isoformat()
        previous_level: int | None = None

        try:
            # Check for existing point
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
                existing_payload = results[0].payload or {}
                previous_level = existing_payload.get("autonomy_level")
                # Merge with existing payload to preserve KB trust fields
                payload = dict(existing_payload)
            else:
                point_id = str(uuid.uuid4())
                payload = {"service_name": service_name}

            # Update autonomy fields
            payload["autonomy_level"] = level
            payload["autonomy_updated_by"] = updated_by
            payload["autonomy_updated_at"] = now
            payload["autonomy_reason"] = reason
            payload["autonomy_previous_level"] = previous_level

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

            return TrustLevelConfig(
                service_name=service_name,
                trust_level=level,
                updated_by=updated_by,
                updated_at=now,
                reason=reason,
                previous_level=previous_level,
            )
        except (UnexpectedResponse, Exception) as e:
            msg = f"Failed to set trust level for {service_name}: {e}"
            logger.warning(msg)
            raise TrustLevelServiceError(msg) from e

    def get_effective_trust_level(self, service_name: str) -> int:
        """Get effective trust level, defaulting to TL1 if not configured.

        Args:
            service_name: Name of the service.

        Returns:
            Trust level integer (1-5), defaults to 1.
        """
        try:
            config = self.get_service_trust_level(service_name)
            if config is None:
                return DEFAULT_TRUST_LEVEL
            return config.trust_level
        except TrustLevelServiceError:
            return DEFAULT_TRUST_LEVEL
