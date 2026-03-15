"""Notification audit service.

Records audit trails for notification deliveries and tracks false pages
when investigations are marked as not-an-issue or inaccurate.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

logger = logging.getLogger(__name__)

AUDIT_COLLECTION = "notification_audit"


class NotificationAuditServiceError(Exception):
    """Error in notification audit service."""

    pass


class NotificationAuditService:
    """Records notification audit trails and manages false page tracking."""

    def __init__(self) -> None:
        self._qdrant_client: QdrantClient | None = None
        self._collection_ensured = False

    @property
    def qdrant_client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            self._qdrant_client = QdrantClient(host=host, port=port)
        return self._qdrant_client

    def close(self) -> None:
        """Close the Qdrant client."""
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None

    @staticmethod
    def _iso_to_epoch(iso_str: str) -> float:
        """Convert an ISO 8601 timestamp string to epoch float."""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, AttributeError):
            return 0.0

    def _ensure_collection(self) -> None:
        """Create the notification_audit collection if it doesn't exist."""
        if self._collection_ensured:
            return
        try:
            self.qdrant_client.get_collection(AUDIT_COLLECTION)
            self._collection_ensured = True
        except (UnexpectedResponse, Exception):
            try:
                self.qdrant_client.create_collection(
                    collection_name=AUDIT_COLLECTION,
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE),
                )
                self._collection_ensured = True
            except Exception as e:
                logger.warning("Failed to create %s collection: %s", AUDIT_COLLECTION, e)

    def record_audit(
        self,
        entry: dict[str, Any],
        channel_config: dict[str, Any],
        delivery_result: dict[str, Any],
    ) -> str:
        """Record an audit trail entry for a notification delivery.

        Args:
            entry: Outbox entry dict with investigation_id, event_type, severity,
                   service, payload.
            channel_config: Channel configuration dict with channel_type, name, config.
            delivery_result: Delivery result dict with status, error, etc.

        Returns:
            The audit_id (UUID string) of the created record.

        Raises:
            NotificationAuditServiceError: If audit recording fails.
        """
        self._ensure_collection()

        audit_id = str(uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        now_epoch = now_dt.timestamp()

        payload = entry.get("payload", {})
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        evidence_summary = payload.get("evidence", [])
        if not isinstance(evidence_summary, list):
            evidence_summary = []

        confidence = payload.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0

        delivery_status = delivery_result.get("status", "unknown")
        delivery_error = delivery_result.get("error", "")
        if delivery_error is None:
            delivery_error = ""

        audit_payload = {
            "audit_id": audit_id,
            "investigation_id": entry.get("investigation_id", ""),
            "event_type": entry.get("event_type", ""),
            "severity": entry.get("severity", ""),
            "service": entry.get("service", ""),
            "channel_type": channel_config.get("channel_type", ""),
            "channel_name": channel_config.get("name", ""),
            "timestamp": now,
            "timestamp_epoch": now_epoch,
            "delivery_status": delivery_status,
            "delivery_error": str(delivery_error),
            "evidence_summary": evidence_summary,
            "confidence": float(confidence),
            "is_false_page": False,
            "false_page_reason": "",
            "false_page_flagged_at": "",
        }

        try:
            self.qdrant_client.upsert(
                collection_name=AUDIT_COLLECTION,
                points=[
                    PointStruct(
                        id=audit_id,
                        vector=[0.0],
                        payload=audit_payload,
                    )
                ],
            )
            return audit_id
        except Exception as e:
            raise NotificationAuditServiceError(
                f"Failed to record audit: {e}"
            ) from e

    def flag_false_pages(self, investigation_id: str, reason: str) -> int:
        """Flag all audit records for an investigation as false pages.

        Args:
            investigation_id: The investigation ID to flag.
            reason: The false page reason (e.g., false_positive, expected_behavior,
                    incorrect_accuracy).

        Returns:
            The number of audit records flagged.

        Raises:
            NotificationAuditServiceError: If flagging fails.
        """
        self._ensure_collection()

        try:
            results, _ = self.qdrant_client.scroll(
                collection_name=AUDIT_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1000,
                with_payload=False,
                with_vectors=False,
            )

            if not results:
                return 0

            now = datetime.now(timezone.utc).isoformat()
            point_ids = [point.id for point in results]

            self.qdrant_client.set_payload(
                collection_name=AUDIT_COLLECTION,
                payload={
                    "is_false_page": True,
                    "false_page_reason": reason,
                    "false_page_flagged_at": now,
                },
                points=point_ids,
            )

            return len(point_ids)
        except Exception as e:
            raise NotificationAuditServiceError(
                f"Failed to flag false pages: {e}"
            ) from e

    def query_audit(
        self,
        service: str | None = None,
        channel_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        is_false_page: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query notification audit records with optional filters.

        Args:
            service: Filter by service name.
            channel_type: Filter by channel type (slack, pagerduty, email, webhook).
            date_from: ISO 8601 start date (inclusive).
            date_to: ISO 8601 end date (inclusive).
            is_false_page: Filter by false page status.
            limit: Maximum records to return (default 50, max 200).
            offset: Number of records to skip (for pagination).

        Returns:
            List of audit record dicts.
        """
        self._ensure_collection()

        limit = min(max(1, limit), 200)
        offset = max(0, offset)

        conditions: list[FieldCondition] = []

        if service is not None:
            conditions.append(
                FieldCondition(key="service", match=MatchValue(value=service))
            )
        if channel_type is not None:
            conditions.append(
                FieldCondition(key="channel_type", match=MatchValue(value=channel_type))
            )
        if is_false_page is not None:
            conditions.append(
                FieldCondition(key="is_false_page", match=MatchValue(value=is_false_page))
            )
        if date_from is not None or date_to is not None:
            range_params: dict[str, Any] = {}
            if date_from is not None:
                range_params["gte"] = self._iso_to_epoch(date_from)
            if date_to is not None:
                range_params["lte"] = self._iso_to_epoch(date_to)
            if range_params:
                conditions.append(
                    FieldCondition(key="timestamp_epoch", range=Range(**range_params))
                )

        scroll_filter = Filter(must=conditions) if conditions else None

        try:
            all_results = []
            scroll_offset = None
            fetched = 0

            # Scroll through results to handle offset
            while True:
                batch_limit = min(limit + offset - fetched, 100)
                if batch_limit <= 0:
                    break

                results, next_offset = self.qdrant_client.scroll(
                    collection_name=AUDIT_COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=batch_limit,
                    offset=scroll_offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in results:
                    if fetched >= offset:
                        all_results.append(point.payload if point.payload else {})
                    fetched += 1
                    if len(all_results) >= limit:
                        break

                if len(all_results) >= limit or next_offset is None:
                    break
                scroll_offset = next_offset

            return all_results
        except Exception as e:
            logger.warning("Failed to query audit records: %s", e)
            return []

    def get_audit_statistics(
        self,
        service: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Get audit statistics (total notifications, false page count, rate).

        Args:
            service: Filter by service name.
            date_from: ISO 8601 start date (inclusive).
            date_to: ISO 8601 end date (inclusive).

        Returns:
            Dict with total_notifications, false_page_count, false_page_rate.
        """
        self._ensure_collection()

        conditions: list[FieldCondition] = []

        if service is not None:
            conditions.append(
                FieldCondition(key="service", match=MatchValue(value=service))
            )
        if date_from is not None or date_to is not None:
            range_params: dict[str, Any] = {}
            if date_from is not None:
                range_params["gte"] = self._iso_to_epoch(date_from)
            if date_to is not None:
                range_params["lte"] = self._iso_to_epoch(date_to)
            if range_params:
                conditions.append(
                    FieldCondition(key="timestamp_epoch", range=Range(**range_params))
                )

        base_filter = Filter(must=conditions) if conditions else None

        try:
            # Count total notifications
            total = self.qdrant_client.count(
                collection_name=AUDIT_COLLECTION,
                count_filter=base_filter,
                exact=True,
            ).count

            # Count false pages
            false_page_conditions = list(conditions)
            false_page_conditions.append(
                FieldCondition(key="is_false_page", match=MatchValue(value=True))
            )
            false_page_count = self.qdrant_client.count(
                collection_name=AUDIT_COLLECTION,
                count_filter=Filter(must=false_page_conditions),
                exact=True,
            ).count

            false_page_rate = (
                false_page_count / total if total > 0 else 0.0
            )

            return {
                "total_notifications": total,
                "false_page_count": false_page_count,
                "false_page_rate": round(false_page_rate, 4),
            }
        except Exception as e:
            logger.warning("Failed to get audit statistics: %s", e)
            return {
                "total_notifications": 0,
                "false_page_count": 0,
                "false_page_rate": 0.0,
            }
