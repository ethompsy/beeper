"""Automatic KB entry creation from resolved investigations (FR38).

Provides duplicate-aware KB entry creation that checks for semantic
similarity before creating new entries. When a similar entry exists,
enriches it instead of duplicating.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from qdrant_client.models import PointStruct

from beeper_investigator.kb.client import (
    KNOWLEDGE_COLLECTION,
    VERSIONS_COLLECTION,
    KBClient,
)
from beeper_investigator.llm.client import LlmClient

logger = logging.getLogger(__name__)

_DEFAULT_BUFFER_DIR = "/tmp/beeper-buffer"
_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0]
_DEFAULT_VECTOR_DIM = 1536

# Similarity thresholds for duplicate detection
SIMILARITY_THRESHOLD = 0.85  # Above this = definite duplicate, enrich
ENRICHMENT_THRESHOLD = 0.70  # Above this = likely related, enrich cautiously


class AutoKBCreationService:
    """Create or update KB entries from resolved investigations.

    Performs semantic similarity check before creating entries to prevent
    duplicates. When a similar entry exists, enriches it with new evidence
    and versions the update.
    """

    def __init__(self, kb_client: KBClient, llm_client: LlmClient) -> None:
        self.kb_client = kb_client
        self.llm_client = llm_client

    def create_or_update_from_investigation(
        self, investigation_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update a KB entry from resolved investigation data.

        Args:
            investigation_data: Dict with investigation context, findings,
                and pipeline metadata.

        Returns:
            Dict with action ("created"/"enriched"/"skipped"), entry_id,
            and similar_score.
        """
        summary_text = self._build_summary_text(investigation_data)
        if not summary_text:
            logger.warning("Empty summary text, skipping KB entry creation")
            return {
                "action": "skipped",
                "entry_id": None,
                "similar_score": None,
                "reason": "empty_summary",
            }

        # Generate embedding
        embedding, embedding_ok = self._generate_embedding(summary_text)

        # Search for similar existing entries
        best_match = self._find_best_match(
            embedding, investigation_data.get("service", "")
        )
        best_score = best_match.score if best_match else None

        if best_match is not None and best_match.score >= ENRICHMENT_THRESHOLD:
            entry_id = self._enrich_existing_entry(
                existing_point_id=best_match.id,
                existing_payload=best_match.payload,
                new_data=investigation_data,
                new_embedding=embedding,
            )
            return {
                "action": "enriched",
                "entry_id": entry_id,
                "similar_score": best_score,
            }

        # No similar entry found — create new
        entry_id = self._create_new_entry(investigation_data, embedding)
        return {
            "action": "created",
            "entry_id": entry_id,
            "similar_score": best_score,
        }

    def _build_summary_text(self, data: dict[str, Any]) -> str:
        """Compose summary text from investigation data for embedding."""
        parts: list[str] = []

        condition = data.get("condition", "")
        service = data.get("service", "")
        if condition and service:
            parts.append(f"{condition} on {service}.")

        root_cause = data.get("root_cause_hypothesis", "")
        if root_cause:
            parts.append(f"Root cause: {root_cause}.")

        signals = data.get("signals_summary", "")
        if signals:
            parts.append(f"Signals: {signals}.")

        doc_summary = data.get("documentation_summary", "")
        if doc_summary:
            parts.append(doc_summary)

        resolution = data.get("resolution", "")
        if not resolution:
            # Try extracting from recommendations
            recommendations = data.get("recommendations", [])
            if recommendations and isinstance(recommendations[0], dict):
                resolution = recommendations[0].get("action", "")
        if resolution:
            parts.append(f"Resolution: {resolution}.")

        result = " ".join(parts)
        return result[:1000] if result else ""

    def _generate_embedding(
        self, summary_text: str
    ) -> tuple[list[float], bool]:
        """Generate embedding vector from summary text."""
        if not summary_text:
            return [0.0] * _DEFAULT_VECTOR_DIM, False

        try:
            embedding = self.llm_client.embed_sync(summary_text)
            return embedding, True
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return [0.0] * _DEFAULT_VECTOR_DIM, False

    def _find_best_match(
        self, embedding: list[float], service: str
    ) -> Optional[Any]:
        """Search for the best matching existing KB entry.

        Returns the top result regardless of score, or None if no results.
        """
        try:
            results = self.kb_client.search_knowledge(
                query_vector=embedding,
                limit=5,
                service=service if service else None,
            )
            if results:
                return results[0]
            return None
        except Exception as exc:
            logger.warning(
                "Similarity search failed, will create new entry: %s", exc
            )
            return None

    def _create_new_entry(
        self,
        data: dict[str, Any],
        embedding: list[float],
    ) -> Optional[str]:
        """Create a new KB entry from investigation data."""
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Build comprehensive content markdown
        content_parts: list[str] = []
        root_cause = data.get("root_cause_hypothesis", "")
        if root_cause:
            content_parts.append(f"## Root Cause\n{root_cause}")

        signals = data.get("signals_summary", "")
        if signals:
            content_parts.append(f"## Symptoms & Signals\n{signals}")

        recommendations = data.get("recommendations", [])
        if recommendations:
            rec_lines = []
            for r in recommendations[:5]:
                if isinstance(r, dict):
                    action = r.get("action", "")
                    if action:
                        rec_lines.append(f"- {action}")
            if rec_lines:
                content_parts.append(
                    "## Resolution Steps\n" + "\n".join(rec_lines)
                )

        evidence = data.get("supporting_evidence", [])
        if evidence:
            ev_lines = [f"- {e}" for e in evidence if isinstance(e, str)]
            if ev_lines:
                content_parts.append(
                    "## Evidence\n" + "\n".join(ev_lines)
                )

        content = "\n\n".join(content_parts) if content_parts else ""

        title = data.get("documentation_title", "")
        if not title:
            title = f"{data.get('condition', 'Unknown')} - {data.get('service', 'Unknown')}"

        investigation_id = data.get("investigation_id", "")

        payload: dict[str, Any] = {
            "entry_id": entry_id,
            "entry_type": "investigation",
            "validation_status": "AI-generated",
            "service": data.get("service", ""),
            "condition": data.get("condition", ""),
            "severity": data.get("severity", ""),
            "created_at": now,
            "updated_at": now,
            "title": title,
            "summary": data.get("documentation_summary", ""),
            "content": content,
            "root_cause": root_cause,
            "resolution": data.get("resolution", ""),
            "signals_summary": signals,
            "key_findings": data.get("key_findings", []),
            "recommendations": recommendations,
            "source_investigation_id": investigation_id,
            "contributing_investigations": (
                [investigation_id] if investigation_id else []
            ),
            "related_investigations": data.get(
                "related_investigations", []
            ),
            "confidence_level": data.get("confidence_level", ""),
            "confidence_percentage": data.get("confidence_percentage"),
            "customer_impacting": data.get("customer_impacting"),
            "version": 1,
        }

        persisted = self._persist_with_retry(entry_id, payload, embedding)

        if persisted:
            self._save_version_snapshot(entry_id, payload, 1)
            return entry_id

        # Buffer on failure
        self._buffer_to_file(
            data.get("investigation_id", "unknown"),
            payload,
            embedding,
        )
        return entry_id

    def _enrich_existing_entry(
        self,
        existing_point_id: str,
        existing_payload: dict[str, Any],
        new_data: dict[str, Any],
        new_embedding: list[float],
    ) -> Optional[str]:
        """Enrich an existing KB entry with new investigation evidence."""
        entry_id: str = str(existing_payload.get("entry_id", existing_point_id))
        now = datetime.now(timezone.utc).isoformat()

        # Save version snapshot of current state before modifying
        current_version = existing_payload.get("version", 1)
        self._save_version_snapshot(
            entry_id, existing_payload, current_version
        )

        # Merge new evidence
        new_version = current_version + 1
        investigation_id = new_data.get("investigation_id", "")

        # Merge key_findings (deduplicate)
        existing_findings = existing_payload.get("key_findings", [])
        new_findings = new_data.get("key_findings", [])
        merged_findings = list(existing_findings)
        for finding in new_findings:
            if finding not in merged_findings:
                merged_findings.append(finding)

        # Merge contributing_investigations
        existing_contribs = existing_payload.get(
            "contributing_investigations", []
        )
        merged_contribs = list(existing_contribs)
        if investigation_id and investigation_id not in merged_contribs:
            merged_contribs.append(investigation_id)

        # Merge related_investigations
        existing_related = existing_payload.get(
            "related_investigations", []
        )
        new_related = new_data.get("related_investigations", [])
        merged_related = list(set(existing_related + new_related))

        # Update payload
        updated_payload = dict(existing_payload)
        updated_payload.update({
            "updated_at": now,
            "version": new_version,
            "key_findings": merged_findings,
            "contributing_investigations": merged_contribs,
            "related_investigations": merged_related,
        })

        # Enrich resolution if new data has more detail
        new_resolution = new_data.get("resolution", "")
        if new_resolution and len(new_resolution) > len(
            existing_payload.get("resolution", "")
        ):
            updated_payload["resolution"] = new_resolution

        persisted = self._persist_with_retry(
            existing_point_id, updated_payload, new_embedding
        )

        if not persisted:
            self._buffer_to_file(
                new_data.get("investigation_id", "unknown"),
                updated_payload,
                new_embedding,
            )

        return entry_id

    def _save_version_snapshot(
        self,
        entry_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> None:
        """Save a version snapshot to knowledge_versions collection."""
        try:
            version_id = str(uuid.uuid4())
            version_payload = {
                "version_id": version_id,
                "entry_id": entry_id,
                "version": version,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            point = PointStruct(
                id=version_id,
                vector=[0.0] * _DEFAULT_VECTOR_DIM,
                payload=version_payload,
            )
            self.kb_client.client.upsert(VERSIONS_COLLECTION, [point])
            logger.info(
                "Saved version snapshot v%d for entry %s",
                version,
                entry_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to save version snapshot for %s: %s",
                entry_id,
                exc,
            )

    def _persist_with_retry(
        self,
        point_id: str,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> bool:
        """Persist KB entry with retry logic."""
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                self.kb_client.client.upsert(
                    KNOWLEDGE_COLLECTION, [point]
                )
                logger.info(
                    "Persisted auto KB entry to knowledge collection"
                )
                return True
            except Exception as exc:
                logger.warning(
                    "Auto KB write attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAYS[attempt])

        return False

    def _buffer_to_file(
        self,
        investigation_id: str,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> Optional[str]:
        """Write failed KB entry to local buffer file."""
        buffer_dir = os.environ.get(
            "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
        )
        try:
            os.makedirs(buffer_dir, exist_ok=True)
            buffer_path = os.path.join(
                buffer_dir,
                f"auto-kb-{investigation_id}.json",
            )
            buffer_data = {
                "payload": payload,
                "embedding": embedding,
                "collection": KNOWLEDGE_COLLECTION,
                "buffered_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(buffer_path, "w") as f:
                json.dump(buffer_data, f)
            logger.warning("Buffered auto KB entry to %s", buffer_path)
            return buffer_path
        except Exception as exc:
            logger.error("Failed to buffer auto KB entry: %s", exc)
            return None
