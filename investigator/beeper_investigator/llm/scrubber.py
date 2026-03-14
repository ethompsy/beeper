"""PII scrubber for LLM context sanitization.

Ensures no sensitive data (emails, IPs, tokens, passwords, credentials)
is sent to external LLM providers. Applied before every LLM call
regardless of model tier (NFR11).

Scrubbed content is replaced with tagged placeholders (e.g., [SCRUBBED:email])
to preserve semantic context. An audit log of scrubbed content is stored
locally via structured JSON logging — never sent to the LLM.
"""

import copy
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScrubRule:
    """A single PII scrubbing rule with a compiled regex pattern."""

    name: str
    pattern: re.Pattern[str]
    placeholder_tag: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, str | bool]) -> "ScrubRule":
        """Create a ScrubRule from a dictionary (e.g., parsed from JSON config).

        Args:
            data: Dictionary with keys: name, pattern, placeholder_tag, enabled (optional).

        Returns:
            Compiled ScrubRule instance.

        Raises:
            ValueError: If required keys are missing or pattern is invalid.
        """
        name = str(data.get("name", ""))
        pattern_str = str(data.get("pattern", ""))
        placeholder_tag = str(data.get("placeholder_tag", ""))
        enabled = bool(data.get("enabled", True))

        if not name or not pattern_str or not placeholder_tag:
            raise ValueError(
                f"ScrubRule requires name, pattern, and placeholder_tag; got: {data}"
            )

        try:
            compiled = re.compile(pattern_str, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern for rule '{name}': {exc}") from exc

        return cls(name=name, pattern=compiled, placeholder_tag=placeholder_tag, enabled=enabled)


@dataclass
class ScrubAuditEntry:
    """Audit record for a single scrub operation."""

    original_value: str
    scrub_type: str
    field_location: str
    timestamp: str


@dataclass
class ScrubResult:
    """Result of a scrub operation on text."""

    scrubbed_text: str
    audit_entries: list[ScrubAuditEntry] = field(default_factory=list)

    @property
    def scrubbed_count(self) -> int:
        """Number of items scrubbed."""
        return len(self.audit_entries)


# ── Default PII patterns ────────────────────────────────

_DEFAULT_RULES: list[ScrubRule] = [
    # credential_url must come before email to avoid partial matches
    ScrubRule(
        name="credential_url",
        pattern=re.compile(
            r"://[^\s:]+:[^\s@]+@",
        ),
        placeholder_tag="credential_url",
    ),
    ScrubRule(
        name="email",
        pattern=re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        ),
        placeholder_tag="email",
    ),
    ScrubRule(
        name="ipv4_address",
        pattern=re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        ),
        placeholder_tag="ip_address",
    ),
    ScrubRule(
        name="ipv6_address",
        pattern=re.compile(
            r"(?<![\w:])(?:"
            r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}"
            r"|(?:[0-9a-fA-F]{1,4}:){1,7}:"
            r"|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}"
            r"|(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}"
            r"|(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}"
            r"|(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}"
            r"|(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}"
            r"|[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}"
            r"|::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}"
            r"|::1"
            r"|fe80::[0-9a-fA-F:]*"
            r")(?![\w:])",
        ),
        placeholder_tag="ipv6_address",
    ),
    ScrubRule(
        name="jwt_token",
        pattern=re.compile(
            r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
        ),
        placeholder_tag="jwt_token",
    ),
    ScrubRule(
        name="bearer_token",
        pattern=re.compile(
            r"Bearer\s+[A-Za-z0-9._~+/=\-]{10,}",
        ),
        placeholder_tag="bearer_token",
    ),
    ScrubRule(
        name="api_key_sk",
        pattern=re.compile(
            r"\bsk-[A-Za-z0-9]{20,}\b",
        ),
        placeholder_tag="api_key",
    ),
    ScrubRule(
        name="api_key_github",
        pattern=re.compile(
            r"\b(?:ghp_|gho_|ghs_|ghr_)[A-Za-z0-9]{30,}\b",
        ),
        placeholder_tag="api_key",
    ),
    ScrubRule(
        name="api_key_slack",
        pattern=re.compile(
            r"\bxox[bpras]-[A-Za-z0-9\-]{10,}\b",
        ),
        placeholder_tag="api_key",
    ),
    ScrubRule(
        name="aws_key",
        pattern=re.compile(
            r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        ),
        placeholder_tag="aws_key",
    ),
    ScrubRule(
        name="password",
        pattern=re.compile(
            r"(?:password|passwd|pwd|secret)\s*[:=]\s*\S+",
            re.IGNORECASE,
        ),
        placeholder_tag="password",
    ),
]


class PiiScrubber:
    """PII scrubber that applies regex-based rules to sanitize text before LLM calls.

    Thread-safe: compiled regex patterns are immutable; rule list operations
    are append-only in practice and safe for concurrent reads.
    """

    def __init__(self, custom_rules: list[ScrubRule] | None = None) -> None:
        """Initialize the scrubber with default + optional custom rules.

        Args:
            custom_rules: Additional scrub rules that merge with (not replace) defaults.
        """
        self._rules: list[ScrubRule] = list(_DEFAULT_RULES)
        if custom_rules:
            self._rules.extend(custom_rules)

    @classmethod
    def from_env(cls) -> "PiiScrubber":
        """Create a PiiScrubber loading custom rules from BEEPER_SCRUB_RULES_JSON env var.

        The env var should contain a JSON array of rule objects:
        [{"name": "phone", "pattern": "\\\\d{3}-\\\\d{4}", "placeholder_tag": "phone"}]

        Returns:
            Configured PiiScrubber instance.
        """
        rules_json = os.environ.get("BEEPER_SCRUB_RULES_JSON", "")
        custom_rules: list[ScrubRule] = []

        if rules_json:
            try:
                raw_rules = json.loads(rules_json)
                if not isinstance(raw_rules, list):
                    logger.warning("BEEPER_SCRUB_RULES_JSON must be a JSON array; ignoring")
                else:
                    for rule_data in raw_rules:
                        try:
                            custom_rules.append(ScrubRule.from_dict(rule_data))
                        except ValueError as exc:
                            logger.warning("Skipping invalid custom scrub rule: %s", exc)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON in BEEPER_SCRUB_RULES_JSON: %s", exc)

        return cls(custom_rules=custom_rules or None)

    @property
    def rules(self) -> list[ScrubRule]:
        """Return a copy of the current rule set."""
        return list(self._rules)

    def add_rule(self, rule: ScrubRule) -> None:
        """Add a custom scrub rule at runtime (applies immediately without restart).

        Args:
            rule: The ScrubRule to add.
        """
        self._rules.append(rule)
        logger.info("Added scrub rule: %s", rule.name)

    def remove_rule(self, name: str) -> bool:
        """Remove a scrub rule by name.

        Args:
            name: The rule name to remove.

        Returns:
            True if a rule was removed, False if not found.
        """
        original_len = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        removed = len(self._rules) < original_len
        if removed:
            logger.info("Removed scrub rule: %s", name)
        return removed

    def scrub_text(self, text: str, field_location: str = "unknown") -> ScrubResult:
        """Scrub PII from a single text string.

        Args:
            text: The text to scrub.
            field_location: Description of where this text came from (for audit).

        Returns:
            ScrubResult with scrubbed text and audit entries.
        """
        if not text:
            return ScrubResult(scrubbed_text=text)

        audit_entries: list[ScrubAuditEntry] = []
        scrubbed = text
        now = datetime.now(timezone.utc).isoformat()

        for rule in self._rules:
            if not rule.enabled:
                continue

            matches = list(rule.pattern.finditer(scrubbed))
            if not matches:
                continue

            # Collect original values for audit trail
            for match in matches:
                original_value = match.group(0)
                audit_entries.append(
                    ScrubAuditEntry(
                        original_value=original_value,
                        scrub_type=rule.placeholder_tag,
                        field_location=field_location,
                        timestamp=now,
                    )
                )

            placeholder = f"[SCRUBBED:{rule.placeholder_tag}]"
            scrubbed = rule.pattern.sub(placeholder, scrubbed)

        return ScrubResult(scrubbed_text=scrubbed, audit_entries=audit_entries)

    def scrub_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], list[ScrubAuditEntry]]:
        """Scrub PII from a list of LLM messages (deep copy — original unmodified).

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Tuple of (scrubbed_messages_copy, all_audit_entries).
        """
        scrubbed_messages = copy.deepcopy(messages)
        all_audit_entries: list[ScrubAuditEntry] = []

        for i, msg in enumerate(scrubbed_messages):
            content = msg.get("content", "")
            if not content:
                continue

            role = msg.get("role", "unknown")
            field_loc = f"message[{i}].content (role={role})"
            result = self.scrub_text(content, field_location=field_loc)
            msg["content"] = result.scrubbed_text
            all_audit_entries.extend(result.audit_entries)

        return scrubbed_messages, all_audit_entries

    def log_audit(
        self,
        audit_entries: list[ScrubAuditEntry],
        method: str,
        investigation_id: str = "",
    ) -> None:
        """Log audit entries for scrubbed PII via structured JSON logging.

        Summary is logged at INFO level. Individual scrubbed values
        are logged at DEBUG level only (for forensic analysis).

        Args:
            audit_entries: List of audit entries from a scrub operation.
            method: The LLM client method that triggered scrubbing (e.g., "complete_sync").
            investigation_id: Optional investigation ID for correlation.
        """
        if not audit_entries:
            return

        scrub_types = list({e.scrub_type for e in audit_entries})
        logger.info(
            json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "INFO",
                "component": "investigator",
                "message": "PII scrubbed from LLM context",
                "context": {
                    "investigation_id": investigation_id,
                    "scrub_count": len(audit_entries),
                    "scrub_types": scrub_types,
                    "method": method,
                },
            })
        )

        for entry in audit_entries:
            logger.debug(
                "Scrubbed %s from %s: %s",
                entry.scrub_type,
                entry.field_location,
                entry.original_value,
            )
