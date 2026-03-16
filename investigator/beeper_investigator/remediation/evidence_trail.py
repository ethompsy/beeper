"""Evidence trail formatting for auto-PR descriptions.

Generates structured markdown PR bodies and commit messages that
link the full audit chain: anomaly -> investigation -> fix -> PR.
"""

import logging
from typing import Any

from beeper_investigator.context import InvestigationContext

logger = logging.getLogger(__name__)


class EvidenceTrailFormatter:
    """Formats PR bodies and commit messages with investigation evidence."""

    def format_pr_body(
        self,
        context: InvestigationContext,
        pipeline_metadata: dict[str, Any],
        fix_description: str,
    ) -> str:
        """Generate a markdown PR body with full evidence trail.

        Args:
            context: Current investigation context.
            pipeline_metadata: Accumulated data from prior pipeline steps.
            fix_description: Human-readable description of the fix.

        Returns:
            Formatted markdown string.
        """
        sections: list[str] = []

        # Header
        sections.append(
            f"## Beeper Auto-Fix: {context.service} — {context.condition}\n"
        )

        # Fix description
        sections.append(f"**Fix:** {fix_description}\n")

        # Investigation summary
        customer_impacting = pipeline_metadata.get("customer_impacting", "unknown")
        sections.append(
            "### Investigation Summary\n"
            f"- **Investigation ID:** {context.investigation_id}\n"
            f"- **Service:** {context.service}\n"
            f"- **Condition:** {context.condition}\n"
            f"- **Severity:** {context.severity}\n"
            f"- **Namespace:** {context.namespace}\n"
            f"- **Customer Impacting:** {customer_impacting}\n"
        )

        # Root cause analysis
        hypothesis = pipeline_metadata.get("root_cause_hypothesis", "")
        if hypothesis:
            confidence_level = pipeline_metadata.get("confidence_level", "unknown")
            confidence_pct = pipeline_metadata.get("confidence_percentage", "N/A")
            evidence_items = pipeline_metadata.get("supporting_evidence", [])

            evidence_text = ""
            if evidence_items:
                evidence_lines = [f"- {item}" for item in evidence_items]
                evidence_text = (
                    "\n**Supporting Evidence:**\n" + "\n".join(evidence_lines) + "\n"
                )

            sections.append(
                "### Root Cause Analysis\n"
                f"**Hypothesis:** {hypothesis}\n"
                f"**Confidence:** {confidence_level} ({confidence_pct}%)\n"
                f"{evidence_text}"
            )

        # Log correlation evidence
        signal_summary = pipeline_metadata.get("signal_summary", "")
        if signal_summary:
            layers = pipeline_metadata.get("layers_queried", [])
            layers_text = ", ".join(layers) if layers else "N/A"
            sections.append(
                "### Log Correlation Evidence\n"
                f"{signal_summary}\n\n"
                f"**Data Sources Queried:** {layers_text}\n"
            )

        # Production conditions
        sections.append(
            "### Production Conditions\n"
            f"- **Severity:** {context.severity}\n"
            f"- **Customer Impacting:** {customer_impacting}\n"
        )

        # Advisory test plan (if available from step 8)
        if pipeline_metadata.get("test_plan_generated"):
            steps = pipeline_metadata.get("verification_steps", [])
            if steps:
                step_lines = []
                for s in steps:
                    if isinstance(s, dict):
                        num = s.get("step_number", "?")
                        title = s.get("title", "Untitled")
                        action = s.get("action", "")
                        step_lines.append(f"{num}. **{title}** — {action}")
                    else:
                        logger.warning(
                            "Skipping non-dict verification step: %s", type(s).__name__
                        )
                sections.append(
                    "### Advisory Test Plan\n" + "\n".join(step_lines) + "\n"
                )

        # Sandbox test results (if executed)
        if pipeline_metadata.get("sandbox_executed"):
            overall = pipeline_metadata.get("sandbox_overall_status", "unknown")
            sandbox_results = pipeline_metadata.get("sandbox_test_results", [])
            sandbox_ns = pipeline_metadata.get("sandbox_namespace", "unknown")
            sandbox_lines = [
                "### Sandbox Test Results\n"
                f"**Overall: {overall.upper()}** (namespace: `{sandbox_ns}`)\n"
            ]
            if sandbox_results:
                sandbox_lines.append(
                    "| Step | Title | Status | Expected | Actual | Duration |"
                )
                sandbox_lines.append(
                    "|------|-------|--------|----------|--------|----------|"
                )
                for sr in sandbox_results:
                    if isinstance(sr, dict):
                        sandbox_lines.append(
                            f"| {sr.get('step_number', '?')} "
                            f"| {sr.get('title', '')} "
                            f"| {sr.get('status', '?')} "
                            f"| {sr.get('expected_outcome', '')[:40]} "
                            f"| {sr.get('actual_value', '')[:40]} "
                            f"| {sr.get('duration_seconds', 0):.1f}s |"
                        )
                    else:
                        logger.warning(
                            "Skipping non-dict sandbox result: %s",
                            type(sr).__name__,
                        )
            sections.append("\n".join(sandbox_lines) + "\n")
        elif pipeline_metadata.get("sandbox_executed") is False:
            skip_reason = pipeline_metadata.get("skip_reason", "unknown")
            sections.append(
                f"### Sandbox Test Results\n*Skipped: {skip_reason}*\n"
            )

        # Post-fix verification (if executed)
        if pipeline_metadata.get("verification_executed"):
            v_status = pipeline_metadata.get("verification_status", "unknown")
            window = pipeline_metadata.get("verification_window_minutes", "N/A")
            v_results = pipeline_metadata.get("verification_results", [])
            verification_lines = [
                "### Post-Fix Verification\n"
                f"**Overall: {v_status.upper()}** (window: {window}min)\n"
            ]
            if v_results:
                verification_lines.append(
                    "| Metric | Pre-Fix | Post-Fix | Delta% | Status |"
                )
                verification_lines.append(
                    "|--------|---------|----------|--------|--------|"
                )
                for vr in v_results:
                    if isinstance(vr, dict):
                        pre = vr.get("pre_fix_value", "N/A")
                        post = vr.get("post_fix_value", "N/A")
                        delta = vr.get("delta_pct")
                        delta_str = f"{delta}%" if delta is not None else "N/A"
                        verification_lines.append(
                            f"| {str(vr.get('metric', '?'))[:40]} "
                            f"| {pre} "
                            f"| {post} "
                            f"| {delta_str} "
                            f"| {vr.get('status', '?')} |"
                        )
                    else:
                        logger.warning(
                            "Skipping non-dict verification result: %s",
                            type(vr).__name__,
                        )
            if v_status == "degraded":
                verification_lines.append(
                    "\n**ROLLBACK RECOMMENDED** — metrics degraded after fix.\n"
                )
            sections.append("\n".join(verification_lines) + "\n")
        elif pipeline_metadata.get("verification_executed") is False:
            v_skip_reason = pipeline_metadata.get("verification_skip_reason", "unknown")
            sections.append(
                f"### Post-Fix Verification\n*Skipped: {v_skip_reason}*\n"
            )

        # Trust gate decisions (if evaluated)
        if pipeline_metadata.get("trust_gate_evaluated"):
            tl = pipeline_metadata.get("trust_gate_trust_level", "?")
            threshold = pipeline_metadata.get(
                "trust_gate_confidence_threshold", "?"
            )
            decisions = pipeline_metadata.get("trust_gate_decisions", [])
            rollback_paths = pipeline_metadata.get(
                "trust_gate_rollback_paths", []
            )
            approval_required = pipeline_metadata.get(
                "trust_gate_approval_required", False
            )

            trust_lines = [
                "### Trust Gate Decisions\n"
                f"**Trust Level:** TL{tl} | "
                f"**Confidence Threshold:** {threshold}\n"
            ]

            if approval_required:
                trust_lines.append(
                    "**MANUAL APPROVAL REQUIRED** — "
                    "some actions blocked by confidence gate.\n"
                )

            if decisions:
                trust_lines.append(
                    "| Action | Category | Decision | Confidence | Reason |"
                )
                trust_lines.append(
                    "|--------|----------|----------|------------|--------|"
                )
                for d in decisions:
                    if isinstance(d, dict):
                        conf = d.get("confidence")
                        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
                        trust_lines.append(
                            f"| {str(d.get('action_name', '?'))[:30]} "
                            f"| {d.get('action_category', '?')} "
                            f"| {d.get('action_type', '?')} "
                            f"| {conf_str} "
                            f"| {str(d.get('reason', ''))[:40]} |"
                        )
                    else:
                        logger.warning(
                            "Skipping non-dict trust gate decision: %s",
                            type(d).__name__,
                        )

            if rollback_paths:
                trust_lines.append("\n**Registered Rollback Paths:**\n")
                for rp in rollback_paths:
                    if isinstance(rp, dict):
                        trust_lines.append(
                            f"- {rp.get('action_name', '?')}: "
                            f"{rp.get('rollback_action', '?')}"
                        )

            sections.append("\n".join(trust_lines) + "\n")

        # Proven fix KB entry (if created)
        if pipeline_metadata.get("kb_entry_created"):
            entry_id = pipeline_metadata.get("proven_fix_entry_id", "?")
            kb_lines = [
                "### Proven Fix KB Entry\n"
                f"**KB Entry ID:** `{entry_id}`\n"
                f"**Validation Status:** proven\n"
                f"**Service:** {context.service}\n"
                "This fix has been accumulated in the knowledge base "
                "for future reference.\n"
            ]
            sections.append("\n".join(kb_lines) + "\n")

        # Audit trail
        verification_status = "pending"
        if pipeline_metadata.get("verification_executed"):
            verification_status = pipeline_metadata.get(
                "verification_status", "pending"
            )
        elif pipeline_metadata.get("sandbox_executed"):
            verification_status = pipeline_metadata.get(
                "sandbox_overall_status", "pending"
            )

        kb_step = ""
        if pipeline_metadata.get("kb_entry_created"):
            short_id = str(
                pipeline_metadata.get("proven_fix_entry_id", "?")
            )[:8]
            kb_step = f" → KB entry ({short_id})"

        sections.append(
            "### Audit Trail\n"
            f"anomaly ({context.condition}) → investigation ({context.investigation_id})"
            f" → fix (this PR) → verification ({verification_status}){kb_step}\n"
        )

        # Footer
        sections.append(
            "---\n"
            f"*Generated by [Beeper](https://beeper.dev) "
            f"| Investigation {context.investigation_id}*"
        )

        return "\n".join(sections)

    def format_commit_message(
        self,
        context: InvestigationContext,
        fix_description: str,
    ) -> str:
        """Generate a structured commit message.

        Args:
            context: Current investigation context.
            fix_description: Short description of the fix.

        Returns:
            Formatted commit message string.
        """
        short_desc = fix_description.split("\n")[0][:72] if fix_description else "auto-fix"
        return (
            f"fix({context.service}): {short_desc}\n\n"
            f"Investigation: {context.investigation_id}\n"
            f"Condition: {context.condition}\n"
            f"Severity: {context.severity}"
        )
