"""Proven fix accumulation step for the Beeper investigator pipeline.

Persists verified fixes to the knowledge base with validation_status="proven"
so future investigations can surface them as high-confidence recommendations (FR31).
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client.models import PointStruct

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import (
    KNOWLEDGE_COLLECTION,
    KBClient,
)
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_DEFAULT_BUFFER_DIR = "/tmp/beeper-buffer"
_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0]
_DEFAULT_VECTOR_DIM = 1536


class ProvenFixAccumulatorStep:
    """Accumulate proven fixes in the knowledge base for future reference (FR31).

    Runs after TrustGateStep as the final pipeline step. Only creates a KB entry
    when MetricVerifierStep has confirmed the fix (fix_proven=True).
    """

    name: str = "Proven Fix Accumulation"

    def __init__(
        self,
        llm_client: LlmClient,
        kb_client: KBClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.kb_client = kb_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Run the proven fix accumulation step."""
        self.status_updater.update_message("Checking for proven fix to accumulate")

        if not self.pipeline_metadata.get("fix_proven"):
            logger.info(
                "No proven fix to accumulate: fix_proven=%s",
                self.pipeline_metadata.get("fix_proven"),
            )
            return StepResult(
                success=True,
                summary="No proven fix to accumulate",
                data={
                    "kb_entry_created": False,
                    "proven_fix_skip_reason": "fix_not_proven",
                },
            )

        self.status_updater.update_message("Accumulating proven fix in knowledge base")
        logger.info(
            "Accumulating proven fix for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        entry_id = str(uuid.uuid4())
        fix_summary = self._build_fix_summary()
        payload = self._build_proven_fix_payload(entry_id, fix_summary)

        embedding, embedding_ok = self._generate_embedding(fix_summary)
        if not embedding_ok:
            logger.warning("Embedding generation failed for proven fix entry")

        persisted, buffered, buffer_path = self._persist_entry(
            entry_id, payload, embedding
        )

        summary = f"Proven fix accumulated: {payload.get('title', 'unknown')}"
        if not persisted and buffered:
            summary += " (buffered locally)"
        elif not persisted:
            summary += " (persistence failed)"

        skip_reason = None
        if not persisted and not buffered:
            skip_reason = "persistence_failed"

        return StepResult(
            success=True,
            summary=summary,
            data={
                "kb_entry_created": persisted,
                "proven_fix_entry_id": entry_id,
                "proven_fix_skip_reason": skip_reason,
                "proven_fix_buffered": buffered,
                "proven_fix_buffer_path": buffer_path,
            },
        )

    # ── Fix summary generation ─────────────────────────────

    def _build_fix_summary(self) -> str:
        """Generate a searchable text summary for embedding and KB content."""
        parts: list[str] = []

        parts.append(
            f"Proven fix for {self.context.condition} "
            f"on service {self.context.service} "
            f"(severity: {self.context.severity})."
        )

        root_cause = self.pipeline_metadata.get("root_cause_hypothesis", "")
        if root_cause:
            parts.append(f"Root cause: {root_cause}.")

        recommendations = self.pipeline_metadata.get("recommendations", [])
        if recommendations:
            actions = [
                r.get("action", "")
                for r in recommendations
                if isinstance(r, dict) and r.get("action")
            ]
            if actions:
                parts.append(f"Resolution: {actions[0]}.")

        verification_status = self.pipeline_metadata.get("verification_status", "")
        if verification_status:
            parts.append(f"Verification: {verification_status}.")

        verification_results = self.pipeline_metadata.get("verification_results", [])
        if verification_results:
            metric_summaries = []
            for vr in verification_results:
                if isinstance(vr, dict):
                    metric = vr.get("metric", "")
                    delta = vr.get("delta_pct")
                    if metric and delta is not None:
                        metric_summaries.append(f"{metric} improved {abs(delta):.1f}%")
            if metric_summaries:
                parts.append(f"Metrics: {', '.join(metric_summaries)}.")

        return " ".join(parts)

    # ── KB entry payload ───────────────────────────────────

    def _build_proven_fix_payload(
        self,
        entry_id: str,
        fix_summary: str,
    ) -> dict[str, Any]:
        """Build the complete KB entry payload for a proven fix."""
        doc_title = self.pipeline_metadata.get(
            "documentation_title",
            f"{self.context.condition} - {self.context.service}",
        )

        recommendations = self.pipeline_metadata.get("recommendations", [])
        first_action = ""
        if recommendations and isinstance(recommendations[0], dict):
            first_action = recommendations[0].get("action", "")

        verification_results = self.pipeline_metadata.get("verification_results", [])
        verification_evidence = {
            "status": self.pipeline_metadata.get("verification_status", ""),
            "window_minutes": self.pipeline_metadata.get(
                "verification_window_minutes"
            ),
            "results": verification_results,
        }

        return {
            "entry_id": entry_id,
            "entry_type": "proven_fix",
            "validation_status": "proven",
            "service": self.context.service,
            "condition": self.context.condition,
            "severity": self.context.severity,
            "investigation_id": self.context.investigation_id,
            "source_investigation_id": self.context.investigation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": f"Proven Fix: {doc_title}",
            "content": fix_summary,
            "root_cause": self.pipeline_metadata.get(
                "root_cause_hypothesis", ""
            ),
            "resolution": first_action,
            "verification_evidence": verification_evidence,
            "pr_url": self.pipeline_metadata.get("pr_url"),
            "confidence_level": self.pipeline_metadata.get(
                "confidence_level", ""
            ),
            "confidence_percentage": self.pipeline_metadata.get(
                "confidence_percentage"
            ),
        }

    # ── Embedding generation ───────────────────────────────

    def _generate_embedding(
        self, text: str
    ) -> tuple[list[float], bool]:
        """Generate embedding vector from fix summary text.

        Returns:
            Tuple of (embedding_vector, success_flag).
        """
        if not text:
            return [0.0] * _DEFAULT_VECTOR_DIM, False

        try:
            embedding = self.llm_client.embed_sync(text)
            return embedding, True
        except Exception as exc:
            logger.warning(
                "Embedding generation failed for proven fix: %s", exc
            )
            return [0.0] * _DEFAULT_VECTOR_DIM, False

    # ── Persistence with retry ─────────────────────────────

    def _persist_entry(
        self,
        entry_id: str,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> tuple[bool, bool, str | None]:
        """Persist KB entry with retry and buffering.

        Returns:
            Tuple of (persisted, buffered, buffer_path).
        """
        point = PointStruct(
            id=entry_id,
            vector=embedding,
            payload=payload,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                self.kb_client.client.upsert(
                    KNOWLEDGE_COLLECTION, [point]
                )
                logger.info(
                    "Persisted proven fix to knowledge collection: %s",
                    entry_id,
                )
                self._cleanup_buffer()
                return True, False, None
            except Exception as exc:
                logger.warning(
                    "KB write attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAYS[attempt])

        buffer_path = self._buffer_to_file(payload, embedding)
        return False, buffer_path is not None, buffer_path

    def _buffer_to_file(
        self,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> str | None:
        """Write failed KB entry to local buffer file."""
        buffer_dir = os.environ.get(
            "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
        )
        try:
            os.makedirs(buffer_dir, exist_ok=True)
            buffer_path = os.path.join(
                buffer_dir,
                f"{self.context.investigation_id}-proven-fix.json",
            )
            buffer_data = {
                "payload": payload,
                "embedding": embedding,
                "collection": KNOWLEDGE_COLLECTION,
                "buffered_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(buffer_path, "w") as f:
                json.dump(buffer_data, f)
            logger.warning(
                "Buffered proven fix entry to %s", buffer_path
            )
            return buffer_path
        except Exception as exc:
            logger.error(
                "Failed to buffer proven fix entry: %s", exc
            )
            return None

    def _cleanup_buffer(self) -> None:
        """Remove buffer file if it exists after successful persistence."""
        buffer_dir = os.environ.get(
            "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
        )
        buffer_path = os.path.join(
            buffer_dir,
            f"{self.context.investigation_id}-proven-fix.json",
        )
        try:
            if os.path.exists(buffer_path):
                os.remove(buffer_path)
                logger.info(
                    "Cleaned up proven fix buffer file %s", buffer_path
                )
        except Exception as exc:
            logger.warning(
                "Failed to clean up proven fix buffer file: %s", exc
            )
