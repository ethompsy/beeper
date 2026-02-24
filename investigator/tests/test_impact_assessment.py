"""Tests for CustomerImpactStep."""

import json
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.llm.client import LlmClientError
from beeper_investigator.steps.impact_assessment import CustomerImpactStep


def _make_step(
    *,
    llm_response: str = '{"customer_impacting": true, "reasoning": "test"}',
    llm_error: Exception | None = None,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
) -> tuple[CustomerImpactStep, MagicMock, MagicMock]:
    """Build a CustomerImpactStep with mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="inv-test-001",
        namespace="default",
        condition=condition,
        service=service,
        severity=severity,
    )
    mock_llm = MagicMock()
    if llm_error:
        mock_llm.complete_sync.side_effect = llm_error
    else:
        mock_llm.complete_sync.return_value = llm_response
    mock_llm.screening_model = "claude-3-haiku-20240307"

    mock_status = MagicMock()

    step = CustomerImpactStep(
        llm_client=mock_llm,
        context=ctx,
        status_updater=mock_status,
    )
    return step, mock_llm, mock_status


class TestCustomerImpactStep:
    """Tests for the customer impact assessment step."""

    def test_customer_facing_returns_true(self) -> None:
        """Customer-facing condition sets customer_impacting=true."""
        step, *_ = _make_step(
            llm_response='{"customer_impacting": true, "reasoning": "Affects checkout"}',
        )

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] is True
        assert "reasoning" in result.data

    def test_internal_returns_false(self) -> None:
        """Internal/infrastructure condition sets customer_impacting=false."""
        step, *_ = _make_step(
            llm_response='{"customer_impacting": false, "reasoning": "Internal cache rebuild"}',
            condition="Cache rebuild on internal-metrics service",
            service="internal-metrics",
        )

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] is False

    def test_uncertain_returns_unknown(self) -> None:
        """Uncertain impact sets customer_impacting=unknown."""
        step, *_ = _make_step(
            llm_response='{"customer_impacting": "unknown", "reasoning": "Insufficient data"}',
        )

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] == "unknown"

    def test_malformed_json_defaults_to_unknown(self) -> None:
        """Malformed JSON response defaults to customer_impacting=unknown."""
        step, *_ = _make_step(llm_response="This is not JSON at all")

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] == "unknown"

    def test_missing_field_defaults_to_unknown(self) -> None:
        """JSON missing customer_impacting field defaults to unknown."""
        step, *_ = _make_step(llm_response='{"reasoning": "no impact field"}')

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] == "unknown"

    def test_markdown_wrapped_json_parsed(self) -> None:
        """JSON wrapped in markdown code fences is parsed correctly."""
        step, *_ = _make_step(
            llm_response='```json\n{"customer_impacting": true, "reasoning": "test"}\n```',
        )

        result = step.execute()

        assert result.success is True
        assert result.data["customer_impacting"] is True

    def test_llm_call_failure_returns_unknown(self) -> None:
        """LLM call failure results in customer_impacting=unknown."""
        step, *_ = _make_step(llm_error=LlmClientError("API down"))

        result = step.execute()

        assert result.success is False
        assert result.data["customer_impacting"] == "unknown"
        assert result.error is not None

    def test_uses_screening_model(self) -> None:
        """Step passes screening model to complete_sync()."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_kwargs = mock_llm.complete_sync.call_args
        assert call_kwargs[1]["model"] == "claude-3-haiku-20240307"

    def test_low_max_tokens(self) -> None:
        """Step uses low max_tokens for screening efficiency."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_kwargs = mock_llm.complete_sync.call_args
        assert call_kwargs[1]["max_tokens"] <= 256

    def test_prompt_includes_context(self) -> None:
        """LLM prompt includes condition, service, and severity."""
        step, mock_llm, _ = _make_step(
            condition="Memory leak",
            service="auth",
            severity="critical",
        )

        step.execute()

        messages = mock_llm.complete_sync.call_args[0][0]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "Memory leak" in user_msg
        assert "auth" in user_msg
        assert "critical" in user_msg

    def test_step_name(self) -> None:
        """Step has descriptive name."""
        step, *_ = _make_step()
        assert step.name == "Customer Impact Assessment"

    def test_status_update_sent(self) -> None:
        """Step sends status update during execution."""
        step, _, mock_status = _make_step()

        step.execute()

        mock_status.update_message.assert_called()

    def test_case_insensitive_true(self) -> None:
        """LLM returning 'True' (capitalized) is normalized to boolean True."""
        step, *_ = _make_step(
            llm_response='{"customer_impacting": "True", "reasoning": "case test"}',
        )

        result = step.execute()

        assert result.data["customer_impacting"] is True

    def test_case_insensitive_false(self) -> None:
        """LLM returning 'FALSE' (uppercase) is normalized to boolean False."""
        step, *_ = _make_step(
            llm_response='{"customer_impacting": "FALSE", "reasoning": "case test"}',
        )

        result = step.execute()

        assert result.data["customer_impacting"] is False
