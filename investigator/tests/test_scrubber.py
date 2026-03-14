"""Comprehensive tests for PII scrubber module."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from beeper_investigator.llm.client import LlmClient

import pytest

from beeper_investigator.llm.scrubber import (
    PiiScrubber,
    ScrubAuditEntry,
    ScrubResult,
    ScrubRule,
)


class TestScrubRuleCreation:
    """Tests for ScrubRule dataclass and factory."""

    def test_from_dict_valid(self) -> None:
        """Test creating a ScrubRule from a valid dictionary."""
        rule = ScrubRule.from_dict({
            "name": "phone",
            "pattern": r"\d{3}-\d{3}-\d{4}",
            "placeholder_tag": "phone",
        })
        assert rule.name == "phone"
        assert rule.placeholder_tag == "phone"
        assert rule.enabled is True

    def test_from_dict_disabled(self) -> None:
        """Test creating a disabled ScrubRule."""
        rule = ScrubRule.from_dict({
            "name": "test",
            "pattern": r"test",
            "placeholder_tag": "test",
            "enabled": False,
        })
        assert rule.enabled is False

    def test_from_dict_missing_name(self) -> None:
        """Test ValueError when name is missing."""
        with pytest.raises(ValueError, match="requires name"):
            ScrubRule.from_dict({"pattern": r"\d+", "placeholder_tag": "num"})

    def test_from_dict_missing_pattern(self) -> None:
        """Test ValueError when pattern is missing."""
        with pytest.raises(ValueError, match="requires name"):
            ScrubRule.from_dict({"name": "test", "placeholder_tag": "test"})

    def test_from_dict_missing_placeholder(self) -> None:
        """Test ValueError when placeholder_tag is missing."""
        with pytest.raises(ValueError, match="requires name"):
            ScrubRule.from_dict({"name": "test", "pattern": r"\d+"})

    def test_from_dict_invalid_regex(self) -> None:
        """Test ValueError when regex pattern is invalid."""
        with pytest.raises(ValueError, match="Invalid regex"):
            ScrubRule.from_dict({
                "name": "bad",
                "pattern": r"[invalid",
                "placeholder_tag": "bad",
            })


class TestPiiScrubberEmailScrubbing:
    """Tests for email address scrubbing."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_simple_email(self) -> None:
        result = self.scrubber.scrub_text("Contact user@domain.com for help")
        assert result.scrubbed_text == "Contact [SCRUBBED:email] for help"
        assert result.scrubbed_count == 1
        assert result.audit_entries[0].scrub_type == "email"
        assert result.audit_entries[0].original_value == "user@domain.com"

    def test_email_with_plus_tag(self) -> None:
        result = self.scrubber.scrub_text("Email user+tag@domain.co.uk now")
        assert "[SCRUBBED:email]" in result.scrubbed_text
        assert result.scrubbed_count == 1

    def test_email_with_dots(self) -> None:
        result = self.scrubber.scrub_text("first.last@company.org")
        assert result.scrubbed_text == "[SCRUBBED:email]"

    def test_multiple_emails(self) -> None:
        text = "From: alice@example.com To: bob@example.com"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == "From: [SCRUBBED:email] To: [SCRUBBED:email]"
        assert result.scrubbed_count == 2


class TestPiiScrubberIpAddressScrubbing:
    """Tests for IP address scrubbing."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_ipv4_address(self) -> None:
        result = self.scrubber.scrub_text("Server at 192.168.1.1 is down")
        assert result.scrubbed_text == "Server at [SCRUBBED:ip_address] is down"
        assert result.scrubbed_count == 1

    def test_ipv4_public_address(self) -> None:
        result = self.scrubber.scrub_text("Connected from 8.8.8.8")
        assert "[SCRUBBED:ip_address]" in result.scrubbed_text

    def test_ipv4_multiple(self) -> None:
        text = "10.0.0.1 -> 172.16.0.1"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == "[SCRUBBED:ip_address] -> [SCRUBBED:ip_address]"

    def test_ipv6_loopback(self) -> None:
        result = self.scrubber.scrub_text("Bound to ::1 on port 8080")
        assert "[SCRUBBED:ipv6_address]" in result.scrubbed_text

    def test_ipv6_link_local(self) -> None:
        result = self.scrubber.scrub_text("Interface fe80::1 is up")
        assert "[SCRUBBED:ipv6_address]" in result.scrubbed_text

    def test_ipv6_full(self) -> None:
        result = self.scrubber.scrub_text("Address 2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert "[SCRUBBED:ipv6_address]" in result.scrubbed_text


class TestPiiScrubberTokenScrubbing:
    """Tests for token and API key scrubbing."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_jwt_token(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc123def456"
        result = self.scrubber.scrub_text(f"Token: {jwt}")
        assert result.scrubbed_text == "Token: [SCRUBBED:jwt_token]"
        assert result.scrubbed_count == 1

    def test_bearer_token(self) -> None:
        bearer = (
            "Authorization: Bearer "
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signature_here"
        )
        result = self.scrubber.scrub_text(bearer)
        assert "[SCRUBBED:" in result.scrubbed_text
        assert result.scrubbed_count >= 1

    def test_openai_api_key(self) -> None:
        result = self.scrubber.scrub_text("Key: sk-abcdefghijklmnopqrstuvwxyz123456")
        assert "[SCRUBBED:api_key]" in result.scrubbed_text

    def test_github_token(self) -> None:
        result = self.scrubber.scrub_text("Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh")
        assert "[SCRUBBED:api_key]" in result.scrubbed_text

    def test_github_token_variants(self) -> None:
        for prefix in ("gho_", "ghs_", "ghr_"):
            token = f"{prefix}{'A' * 30}"
            result = self.scrubber.scrub_text(f"Token: {token}")
            assert "[SCRUBBED:api_key]" in result.scrubbed_text

    def test_slack_bot_token(self) -> None:
        result = self.scrubber.scrub_text("SLACK_TOKEN=xoxb-1234567890-abcdefghij")
        assert "[SCRUBBED:api_key]" in result.scrubbed_text

    def test_slack_user_token(self) -> None:
        result = self.scrubber.scrub_text("token: xoxp-1234567890-abcdefghij")
        assert "[SCRUBBED:api_key]" in result.scrubbed_text


class TestPiiScrubberPasswordScrubbing:
    """Tests for password and secret scrubbing."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_password_equals(self) -> None:
        result = self.scrubber.scrub_text("password=SuperSecret123!")
        assert "[SCRUBBED:password]" in result.scrubbed_text

    def test_password_colon(self) -> None:
        result = self.scrubber.scrub_text("PASSWORD: mypassword")
        assert "[SCRUBBED:password]" in result.scrubbed_text

    def test_pwd_variant(self) -> None:
        result = self.scrubber.scrub_text("pwd = hunter2")
        assert "[SCRUBBED:password]" in result.scrubbed_text

    def test_secret_variant(self) -> None:
        result = self.scrubber.scrub_text("secret=abc123xyz")
        assert "[SCRUBBED:password]" in result.scrubbed_text

    def test_connection_string_with_password(self) -> None:
        result = self.scrubber.scrub_text("postgres://user:p4ssw0rd@db.host.com:5432/mydb")
        assert "[SCRUBBED:credential_url]" in result.scrubbed_text


class TestPiiScrubberAwsKeyScrubbing:
    """Tests for AWS key scrubbing."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_aws_access_key_akia(self) -> None:
        result = self.scrubber.scrub_text("AWS_KEY=AKIAIOSFODNN7EXAMPLE")
        assert "[SCRUBBED:aws_key]" in result.scrubbed_text

    def test_aws_temp_key_asia(self) -> None:
        result = self.scrubber.scrub_text("Key: ASIAJEXAMPLEEXAMPLE1")
        assert "[SCRUBBED:aws_key]" in result.scrubbed_text


class TestPiiScrubberPlaceholderFormat:
    """Tests for placeholder format correctness."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_email_placeholder(self) -> None:
        result = self.scrubber.scrub_text("test@test.com")
        assert result.scrubbed_text == "[SCRUBBED:email]"

    def test_ip_placeholder(self) -> None:
        result = self.scrubber.scrub_text("10.0.0.1")
        assert result.scrubbed_text == "[SCRUBBED:ip_address]"

    def test_custom_rule_placeholder(self) -> None:
        import re

        rule = ScrubRule(
            name="custom",
            pattern=re.compile(r"CUST-\d{6}"),
            placeholder_tag="customer_id",
        )
        scrubber = PiiScrubber(custom_rules=[rule])
        result = scrubber.scrub_text("Customer CUST-123456")
        assert result.scrubbed_text == "Customer [SCRUBBED:customer_id]"


class TestPiiScrubberAuditEntries:
    """Tests for audit log entry correctness."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_audit_entry_fields(self) -> None:
        result = self.scrubber.scrub_text("user@test.com", field_location="test_field")
        assert len(result.audit_entries) == 1
        entry = result.audit_entries[0]
        assert entry.original_value == "user@test.com"
        assert entry.scrub_type == "email"
        assert entry.field_location == "test_field"
        assert entry.timestamp  # non-empty ISO timestamp

    def test_audit_multiple_entries(self) -> None:
        text = "user@test.com at 10.0.0.1"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_count == 2
        types = {e.scrub_type for e in result.audit_entries}
        assert "email" in types
        assert "ip_address" in types

    def test_audit_entry_timestamp_is_iso(self) -> None:
        result = self.scrubber.scrub_text("user@test.com")
        timestamp = result.audit_entries[0].timestamp
        # ISO 8601 format check
        assert "T" in timestamp
        assert timestamp.endswith("+00:00") or timestamp.endswith("Z")


class TestPiiScrubberScrubMessages:
    """Tests for scrub_messages() method."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_scrub_messages_preserves_structure(self) -> None:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Error from user@test.com at 10.0.0.1"},
        ]
        scrubbed, entries = self.scrubber.scrub_messages(messages)
        assert len(scrubbed) == 2
        assert scrubbed[0]["role"] == "system"
        assert scrubbed[1]["role"] == "user"

    def test_scrub_messages_does_not_modify_original(self) -> None:
        original = [{"role": "user", "content": "user@test.com"}]
        scrubbed, _ = self.scrubber.scrub_messages(original)
        assert original[0]["content"] == "user@test.com"
        assert scrubbed[0]["content"] == "[SCRUBBED:email]"

    def test_scrub_messages_system_and_user(self) -> None:
        messages = [
            {"role": "system", "content": "API key: sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            {"role": "user", "content": "Check logs at 192.168.0.1"},
        ]
        scrubbed, entries = self.scrubber.scrub_messages(messages)
        assert "[SCRUBBED:api_key]" in scrubbed[0]["content"]
        assert "[SCRUBBED:ip_address]" in scrubbed[1]["content"]
        assert len(entries) == 2

    def test_scrub_messages_empty_content(self) -> None:
        messages = [{"role": "user", "content": ""}]
        scrubbed, entries = self.scrubber.scrub_messages(messages)
        assert scrubbed[0]["content"] == ""
        assert len(entries) == 0

    def test_scrub_messages_no_pii(self) -> None:
        messages = [{"role": "user", "content": "Normal text without PII"}]
        scrubbed, entries = self.scrubber.scrub_messages(messages)
        assert scrubbed[0]["content"] == "Normal text without PII"
        assert len(entries) == 0

    def test_scrub_messages_audit_field_location(self) -> None:
        messages = [
            {"role": "system", "content": "system text"},
            {"role": "user", "content": "user@test.com"},
        ]
        _, entries = self.scrubber.scrub_messages(messages)
        assert len(entries) == 1
        assert "message[1].content (role=user)" in entries[0].field_location


class TestPiiScrubberScrubText:
    """Tests for scrub_text() single-string method."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_empty_text(self) -> None:
        result = self.scrubber.scrub_text("")
        assert result.scrubbed_text == ""
        assert result.scrubbed_count == 0

    def test_no_pii_text(self) -> None:
        text = "Server CPU usage is at 95% for the payments service"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text
        assert result.scrubbed_count == 0

    def test_mixed_pii(self) -> None:
        text = "Error for user@test.com from 10.0.0.1 with password=hunter2"
        result = self.scrubber.scrub_text(text)
        assert "[SCRUBBED:email]" in result.scrubbed_text
        assert "[SCRUBBED:ip_address]" in result.scrubbed_text
        assert "[SCRUBBED:password]" in result.scrubbed_text
        assert result.scrubbed_count == 3


class TestPiiScrubberCustomRules:
    """Tests for configurable custom scrub rules."""

    def test_custom_rule_via_constructor(self) -> None:
        import re

        custom = ScrubRule(
            name="phone",
            pattern=re.compile(r"\b\d{3}-\d{3}-\d{4}\b"),
            placeholder_tag="phone",
        )
        scrubber = PiiScrubber(custom_rules=[custom])
        result = scrubber.scrub_text("Call 555-123-4567")
        assert result.scrubbed_text == "Call [SCRUBBED:phone]"

    def test_custom_rules_from_env(self) -> None:
        rules_json = json.dumps([
            {"name": "ticket", "pattern": r"TICKET-\d+", "placeholder_tag": "ticket_id"},
        ])
        with patch.dict(os.environ, {"BEEPER_SCRUB_RULES_JSON": rules_json}):
            scrubber = PiiScrubber.from_env()
            result = scrubber.scrub_text("See TICKET-12345")
            assert result.scrubbed_text == "See [SCRUBBED:ticket_id]"

    def test_custom_rules_merge_with_defaults(self) -> None:
        import re

        custom = ScrubRule(
            name="custom",
            pattern=re.compile(r"CUSTOM-\d+"),
            placeholder_tag="custom_id",
        )
        scrubber = PiiScrubber(custom_rules=[custom])
        # Default email rule still works
        result = scrubber.scrub_text("user@test.com and CUSTOM-123")
        assert "[SCRUBBED:email]" in result.scrubbed_text
        assert "[SCRUBBED:custom_id]" in result.scrubbed_text

    def test_add_rule_at_runtime(self) -> None:
        import re

        scrubber = PiiScrubber()
        rule = ScrubRule(
            name="ssn",
            pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            placeholder_tag="ssn",
        )
        scrubber.add_rule(rule)
        result = scrubber.scrub_text("SSN: 123-45-6789")
        assert result.scrubbed_text == "SSN: [SCRUBBED:ssn]"

    def test_remove_rule_at_runtime(self) -> None:
        scrubber = PiiScrubber()
        assert scrubber.remove_rule("email") is True
        result = scrubber.scrub_text("user@test.com")
        assert result.scrubbed_text == "user@test.com"  # No longer scrubbed

    def test_remove_nonexistent_rule(self) -> None:
        scrubber = PiiScrubber()
        assert scrubber.remove_rule("nonexistent") is False

    def test_disabled_rule_not_applied(self) -> None:
        import re

        disabled_rule = ScrubRule(
            name="disabled_test",
            pattern=re.compile(r"DISABLED-\d+"),
            placeholder_tag="disabled",
            enabled=False,
        )
        scrubber = PiiScrubber(custom_rules=[disabled_rule])
        result = scrubber.scrub_text("DISABLED-123")
        assert result.scrubbed_text == "DISABLED-123"

    def test_env_var_invalid_json(self) -> None:
        with patch.dict(os.environ, {"BEEPER_SCRUB_RULES_JSON": "not json"}):
            scrubber = PiiScrubber.from_env()
            # Should still have default rules, just log warning
            assert len(scrubber.rules) > 0

    def test_env_var_invalid_rule_skipped(self) -> None:
        rules_json = json.dumps([
            {"name": "good", "pattern": r"\d+", "placeholder_tag": "num"},
            {"name": "", "pattern": "", "placeholder_tag": ""},  # invalid
        ])
        with patch.dict(os.environ, {"BEEPER_SCRUB_RULES_JSON": rules_json}):
            scrubber = PiiScrubber.from_env()
            # Default rules + 1 valid custom rule; invalid skipped
            rule_names = [r.name for r in scrubber.rules]
            assert "good" in rule_names

    def test_env_var_not_array(self) -> None:
        with patch.dict(os.environ, {"BEEPER_SCRUB_RULES_JSON": '{"key": "val"}'}):
            scrubber = PiiScrubber.from_env()
            # Should still have default rules
            assert len(scrubber.rules) > 0

    def test_configurable_rules_apply_without_restart(self) -> None:
        import re

        scrubber = PiiScrubber()
        # Initially no custom rule
        result = scrubber.scrub_text("CONF-999")
        assert result.scrubbed_text == "CONF-999"

        # Add rule at runtime
        scrubber.add_rule(ScrubRule(
            name="conf",
            pattern=re.compile(r"CONF-\d+"),
            placeholder_tag="config_id",
        ))

        # Now it scrubs
        result = scrubber.scrub_text("CONF-999")
        assert result.scrubbed_text == "[SCRUBBED:config_id]"


class TestPiiScrubberNoFalsePositives:
    """Tests ensuring normal operational text is NOT scrubbed."""

    def setup_method(self) -> None:
        self.scrubber = PiiScrubber()

    def test_service_names_not_scrubbed(self) -> None:
        text = "Service payments-api is degraded"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text
        assert result.scrubbed_count == 0

    def test_metric_names_not_scrubbed(self) -> None:
        text = "http_requests_total{service='payments'} increased by 200%"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text

    def test_prometheus_query_not_scrubbed(self) -> None:
        text = 'rate(http_request_duration_seconds_count{job="api"}[5m])'
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text

    def test_normal_numbers_not_scrubbed(self) -> None:
        text = "CPU at 95%, memory 2048MB, latency 250ms"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text

    def test_version_numbers_not_scrubbed(self) -> None:
        text = "Running version 3.11.2 of Python"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text

    def test_kubernetes_labels_not_scrubbed(self) -> None:
        text = "pod: payments-api-7f8b9d6c4d-2xk9m namespace: production"
        result = self.scrubber.scrub_text(text)
        assert result.scrubbed_text == text

    def test_kubernetes_secret_ref_not_scrubbed(self) -> None:
        """Verify K8s resource names with 'secret' prefix are not falsely scrubbed."""
        text = "secretName: my-app-credentials secretRef: db-secret"
        result = self.scrubber.scrub_text(text)
        # secretName and secretRef should NOT match — the password regex requires
        # 'secret' followed by optional whitespace then ':' or '=', not 'N' or 'R'.
        assert result.scrubbed_text == text


class TestLlmClientScrubberIntegration:
    """Tests for scrubber integration in LlmClient methods."""

    @staticmethod
    def _make_client() -> "LlmClient":
        from beeper_investigator.llm.client import LlmClient, LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            cache_enabled=False,
        )
        return LlmClient(config)

    def test_client_has_scrubber(self) -> None:
        client = self._make_client()
        assert hasattr(client, "scrubber")
        assert isinstance(client.scrubber, PiiScrubber)

    @patch("litellm.completion")
    def test_complete_sync_scrubs_before_llm(self, mock_completion: MagicMock) -> None:
        """Verify complete_sync() sends scrubbed messages to LiteLLM."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        mock_response.usage = None
        mock_completion.return_value = mock_response

        client = self._make_client()
        messages = [{"role": "user", "content": "Error from user@test.com"}]
        client.complete_sync(messages)

        # Verify LiteLLM received scrubbed messages
        actual_messages = mock_completion.call_args[1]["messages"]
        assert "[SCRUBBED:email]" in actual_messages[0]["content"]
        assert "user@test.com" not in actual_messages[0]["content"]

    @patch("litellm.completion")
    def test_complete_sync_preserves_original_messages(
        self, mock_completion: MagicMock
    ) -> None:
        """Verify complete_sync() does not modify the original messages list."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        mock_response.usage = None
        mock_completion.return_value = mock_response

        client = self._make_client()
        original_messages = [{"role": "user", "content": "user@test.com"}]
        client.complete_sync(original_messages)

        # Original messages must be untouched
        assert original_messages[0]["content"] == "user@test.com"

    @patch("litellm.acompletion")
    @pytest.mark.asyncio
    async def test_complete_async_scrubs_before_llm(
        self, mock_acompletion: MagicMock
    ) -> None:
        """Verify complete() (async) sends scrubbed messages to LiteLLM."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        mock_response.usage = None
        mock_acompletion.return_value = mock_response

        client = self._make_client()
        messages = [{"role": "user", "content": "Error from user@test.com"}]
        await client.complete(messages)

        actual_messages = mock_acompletion.call_args[1]["messages"]
        assert "[SCRUBBED:email]" in actual_messages[0]["content"]

    @patch("litellm.embedding")
    def test_embed_sync_scrubs_before_llm(self, mock_embedding: MagicMock) -> None:
        """Verify embed_sync() scrubs text before sending to LiteLLM."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_embedding.return_value = mock_response

        from beeper_investigator.llm.client import LlmClient, LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            embedding_model="text-embedding-3-small",
        )
        client = LlmClient(config)
        client.embed_sync("Error from user@test.com")

        actual_input = mock_embedding.call_args[1]["input"]
        assert "[SCRUBBED:email]" in actual_input[0]
        assert "user@test.com" not in actual_input[0]


class TestPiiScrubberAuditLogging:
    """Tests for audit log output."""

    def test_log_audit_calls_logger(self) -> None:
        scrubber = PiiScrubber()
        entries = [
            ScrubAuditEntry(
                original_value="user@test.com",
                scrub_type="email",
                field_location="test",
                timestamp="2026-01-01T00:00:00+00:00",
            )
        ]
        with patch("beeper_investigator.llm.scrubber.logger") as mock_logger:
            scrubber.log_audit(entries, method="complete_sync")
            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            parsed = json.loads(log_msg)
            assert parsed["message"] == "PII scrubbed from LLM context"
            assert parsed["context"]["scrub_count"] == 1
            assert parsed["context"]["method"] == "complete_sync"
            assert "email" in parsed["context"]["scrub_types"]

    def test_log_audit_empty_entries_no_log(self) -> None:
        scrubber = PiiScrubber()
        with patch("beeper_investigator.llm.scrubber.logger") as mock_logger:
            scrubber.log_audit([], method="complete_sync")
            mock_logger.info.assert_not_called()

    def test_log_audit_debug_entries(self) -> None:
        scrubber = PiiScrubber()
        entries = [
            ScrubAuditEntry(
                original_value="user@test.com",
                scrub_type="email",
                field_location="test",
                timestamp="2026-01-01T00:00:00+00:00",
            )
        ]
        with patch("beeper_investigator.llm.scrubber.logger") as mock_logger:
            scrubber.log_audit(entries, method="test")
            # DEBUG log should be called for each entry
            mock_logger.debug.assert_called_once()

    def test_log_audit_includes_investigation_id(self) -> None:
        """Verify investigation_id appears in the structured log output."""
        scrubber = PiiScrubber()
        entries = [
            ScrubAuditEntry(
                original_value="user@test.com",
                scrub_type="email",
                field_location="test",
                timestamp="2026-01-01T00:00:00+00:00",
            )
        ]
        with patch("beeper_investigator.llm.scrubber.logger") as mock_logger:
            scrubber.log_audit(
                entries, method="complete_sync", investigation_id="inv-abc123"
            )
            log_msg = mock_logger.info.call_args[0][0]
            parsed = json.loads(log_msg)
            assert parsed["context"]["investigation_id"] == "inv-abc123"


class TestCredentialNonPersistence:
    """Tests verifying credentials are never stored in persistent storage."""

    def test_llm_config_credentials_not_in_qdrant(self) -> None:
        """Verify LlmConfig does not expose methods to persist credentials."""
        from beeper_investigator.llm.client import LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-secret-key",
        )
        # Config should NOT have any persistence methods
        assert not hasattr(config, "save")
        assert not hasattr(config, "persist")
        assert not hasattr(config, "to_database")
        assert not hasattr(config, "to_qdrant")

    def test_llm_client_does_not_store_key_externally(self) -> None:
        """Verify LlmClient does not expose credential storage beyond env vars."""
        from beeper_investigator.llm.client import LlmClient, LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-secret-key",
        )
        client = LlmClient(config)
        # Cost stats, cache stats, model usage should NOT contain api_key
        cost_stats = client.get_cost_stats()
        cache_stats = client.get_cache_stats()
        model_usage = client.get_model_usage()

        for stats in (cost_stats, cache_stats, model_usage):
            stats_str = json.dumps(stats, default=str)
            assert "test-secret-key" not in stats_str


class TestScrubResult:
    """Tests for ScrubResult dataclass."""

    def test_scrubbed_count_property(self) -> None:
        result = ScrubResult(scrubbed_text="test")
        assert result.scrubbed_count == 0

    def test_scrubbed_count_with_entries(self) -> None:
        entries = [
            ScrubAuditEntry("val", "type", "loc", "ts"),
            ScrubAuditEntry("val2", "type2", "loc2", "ts2"),
        ]
        result = ScrubResult(scrubbed_text="test", audit_entries=entries)
        assert result.scrubbed_count == 2
