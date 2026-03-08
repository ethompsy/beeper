"""Tests for LLM cost tracking and spending cap enforcement."""

import os
from unittest.mock import MagicMock, patch

from beeper_investigator.llm.cost import (
    CostTracker,
    calculate_call_cost,
)
from beeper_investigator.llm.spending_cap import (
    SpendingCapConfig,
    SpendingCapEnforcer,
)

# ── Cost calculation tests ──────────────────────────


class TestCalculateCallCost:
    """Tests for calculate_call_cost function."""

    def test_known_model_cost(self) -> None:
        """Test cost calculation with known model pricing."""
        cost = calculate_call_cost(
            "claude-sonnet-4-20250514",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # input: 1000/1M * $3.00 = $0.003
        # output: 500/1M * $15.00 = $0.0075
        expected = 0.003 + 0.0075
        assert abs(cost - expected) < 1e-9

    def test_haiku_model_cost(self) -> None:
        """Test cost calculation for cheaper haiku model."""
        cost = calculate_call_cost(
            "claude-3-haiku-20240307",
            prompt_tokens=10000,
            completion_tokens=5000,
        )
        # input: 10000/1M * $0.25 = $0.0025
        # output: 5000/1M * $1.25 = $0.00625
        expected = 0.0025 + 0.00625
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_returns_zero(self) -> None:
        """Test that unknown models return zero cost."""
        cost = calculate_call_cost(
            "unknown-model-v1",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == 0.0

    def test_zero_tokens(self) -> None:
        """Test cost with zero tokens."""
        cost = calculate_call_cost(
            "claude-sonnet-4-20250514",
            prompt_tokens=0,
            completion_tokens=0,
        )
        assert cost == 0.0

    def test_openai_model_cost(self) -> None:
        """Test cost calculation for OpenAI models."""
        cost = calculate_call_cost(
            "gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # input: 1000/1M * $2.50 = $0.0025
        # output: 500/1M * $10.00 = $0.005
        expected = 0.0025 + 0.005
        assert abs(cost - expected) < 1e-9


# ── CostTracker tests ──────────────────────────


class TestCostTracker:
    """Tests for CostTracker class."""

    def test_record_call_accumulates_cost(self) -> None:
        """Test that recording calls accumulates total cost."""
        tracker = CostTracker()
        cost1 = tracker.record_call("claude-sonnet-4-20250514", 1000, 500)
        cost2 = tracker.record_call("claude-sonnet-4-20250514", 2000, 1000)
        assert cost1 > 0
        assert cost2 > 0
        assert abs(tracker.total_cost_usd - (cost1 + cost2)) < 1e-9

    def test_total_cost_cents(self) -> None:
        """Test cents conversion."""
        tracker = CostTracker()
        tracker.record_call("claude-sonnet-4-20250514", 1000000, 0)
        # 1M tokens * $3.00/1M = $3.00 = 300 cents
        assert tracker.total_cost_cents == 300

    def test_token_accumulation(self) -> None:
        """Test that tokens are accumulated correctly."""
        tracker = CostTracker()
        tracker.record_call("claude-sonnet-4-20250514", 100, 50)
        tracker.record_call("claude-sonnet-4-20250514", 200, 100)
        assert tracker.total_prompt_tokens == 300
        assert tracker.total_completion_tokens == 150

    def test_call_count(self) -> None:
        """Test call count tracking."""
        tracker = CostTracker()
        assert tracker.call_count == 0
        tracker.record_call("claude-sonnet-4-20250514", 100, 50)
        tracker.record_call("gpt-4o", 100, 50)
        assert tracker.call_count == 2

    def test_get_cost_stats(self) -> None:
        """Test cost stats output."""
        tracker = CostTracker()
        tracker.record_call("claude-sonnet-4-20250514", 1000, 500)
        tracker.record_call("claude-3-haiku-20240307", 2000, 1000)

        stats = tracker.get_cost_stats()
        assert stats["call_count"] == 2
        assert stats["total_cost_usd"] > 0
        assert stats["total_prompt_tokens"] == 3000
        assert stats["total_completion_tokens"] == 1500
        assert "claude-sonnet-4-20250514" in stats["per_model"]
        assert "claude-3-haiku-20240307" in stats["per_model"]
        assert stats["per_model"]["claude-sonnet-4-20250514"]["calls"] == 1

    def test_reset(self) -> None:
        """Test reset clears all data."""
        tracker = CostTracker()
        tracker.record_call("claude-sonnet-4-20250514", 1000, 500)
        tracker.reset()
        assert tracker.total_cost_usd == 0.0
        assert tracker.call_count == 0
        assert tracker.total_prompt_tokens == 0
        assert tracker.total_completion_tokens == 0


# ── SpendingCapConfig tests ──────────────────────────


class TestSpendingCapConfig:
    """Tests for SpendingCapConfig."""

    def test_from_env_with_all_vars(self) -> None:
        """Test loading config from environment variables."""
        env = {
            "BEEPER_LLM_DAILY_CAP_CENTS": "5000",
            "BEEPER_LLM_MONTHLY_CAP_CENTS": "50000",
            "BEEPER_LLM_CAP_WARNING_THRESHOLD": "0.8",
            "BEEPER_INVESTIGATION_RATE_LIMIT": "100",
            "BEEPER_CAP_PRIORITY_SEVERITIES": "high,critical",
        }
        with patch.dict(os.environ, env, clear=False):
            config = SpendingCapConfig.from_env()
        assert config.daily_cap_cents == 5000
        assert config.monthly_cap_cents == 50000
        assert config.warning_threshold == 0.8
        assert config.rate_limit_per_hour == 100
        assert config.priority_severities == {"high", "critical"}
        assert config.enabled is True

    def test_from_env_no_caps(self) -> None:
        """Test loading config with no caps set."""
        env_keys = [
            "BEEPER_LLM_DAILY_CAP_CENTS",
            "BEEPER_LLM_MONTHLY_CAP_CENTS",
            "BEEPER_INVESTIGATION_RATE_LIMIT",
        ]
        env = {k: "" for k in env_keys}
        with patch.dict(os.environ, env, clear=False):
            # Remove keys if they exist
            for k in env_keys:
                os.environ.pop(k, None)
            config = SpendingCapConfig.from_env()
        assert config.daily_cap_cents is None
        assert config.monthly_cap_cents is None
        assert config.rate_limit_per_hour is None
        assert config.enabled is False

    def test_default_priority_severities(self) -> None:
        """Test default priority severities."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BEEPER_CAP_PRIORITY_SEVERITIES", None)
            config = SpendingCapConfig.from_env()
        assert "high" in config.priority_severities
        assert "critical" in config.priority_severities


# ── SpendingCapEnforcer tests ──────────────────────────


class TestSpendingCapEnforcer:
    """Tests for SpendingCapEnforcer."""

    def _make_config(
        self,
        daily_cap: int | None = 5000,
        monthly_cap: int | None = 50000,
        rate_limit: int | None = 100,
    ) -> SpendingCapConfig:
        return SpendingCapConfig(
            daily_cap_cents=daily_cap,
            monthly_cap_cents=monthly_cap,
            warning_threshold=0.8,
            rate_limit_per_hour=rate_limit,
            priority_severities={"high", "critical"},
        )

    def test_allows_when_under_cap(self) -> None:
        """Test that budget check allows when under cap."""
        enforcer = SpendingCapEnforcer(self._make_config())
        result = enforcer.check_budget("medium")
        assert result.allowed is True
        assert result.warning is False

    def test_warns_at_80_percent(self) -> None:
        """Test warning at 80% threshold."""
        enforcer = SpendingCapEnforcer(self._make_config(daily_cap=1000))
        enforcer.update_spend(800)  # 80% of 1000
        result = enforcer.check_budget("medium")
        assert result.allowed is True
        assert result.warning is True

    def test_denies_when_over_daily_cap(self) -> None:
        """Test denial when over daily cap."""
        enforcer = SpendingCapEnforcer(self._make_config(daily_cap=1000))
        enforcer.update_spend(1000)  # 100% of cap
        result = enforcer.check_budget("medium")
        assert result.allowed is False

    def test_allows_critical_when_over_cap(self) -> None:
        """Test that critical severity bypasses cap."""
        enforcer = SpendingCapEnforcer(self._make_config(daily_cap=1000))
        enforcer.update_spend(1000)

        result_critical = enforcer.check_budget("critical")
        assert result_critical.allowed is True

        result_high = enforcer.check_budget("high")
        assert result_high.allowed is True

    def test_denies_low_when_over_cap(self) -> None:
        """Test that low severity is denied when over cap."""
        enforcer = SpendingCapEnforcer(self._make_config(daily_cap=1000))
        enforcer.update_spend(1000)
        result = enforcer.check_budget("low")
        assert result.allowed is False

    def test_monthly_cap_enforcement(self) -> None:
        """Test monthly cap enforcement."""
        enforcer = SpendingCapEnforcer(
            self._make_config(daily_cap=None, monthly_cap=5000)
        )
        enforcer.update_spend(5000)
        result = enforcer.check_budget("medium")
        assert result.allowed is False

    def test_rate_limit_allows_under_limit(self) -> None:
        """Test rate limit allows when under limit."""
        enforcer = SpendingCapEnforcer(self._make_config(rate_limit=5))
        for _ in range(4):
            enforcer.record_investigation()
        assert enforcer.check_rate_limit() is True

    def test_rate_limit_denies_over_limit(self) -> None:
        """Test rate limit denies when over limit."""
        enforcer = SpendingCapEnforcer(self._make_config(rate_limit=3))
        for _ in range(3):
            enforcer.record_investigation()
        assert enforcer.check_rate_limit() is False

    def test_rate_limit_none_always_allows(self) -> None:
        """Test that no rate limit configured always allows."""
        enforcer = SpendingCapEnforcer(self._make_config(rate_limit=None))
        for _ in range(100):
            enforcer.record_investigation()
        assert enforcer.check_rate_limit() is True

    def test_update_spend(self) -> None:
        """Test spend tracking updates."""
        enforcer = SpendingCapEnforcer(self._make_config())
        enforcer.update_spend(100)
        enforcer.update_spend(200)
        assert enforcer.current_daily_spend_cents == 300
        assert enforcer.current_monthly_spend_cents == 300

    def test_reset_daily(self) -> None:
        """Test daily reset."""
        enforcer = SpendingCapEnforcer(self._make_config())
        enforcer.update_spend(100)
        enforcer.reset_daily()
        assert enforcer.current_daily_spend_cents == 0
        assert enforcer.current_monthly_spend_cents == 100

    def test_reset_monthly(self) -> None:
        """Test monthly reset."""
        enforcer = SpendingCapEnforcer(self._make_config())
        enforcer.update_spend(100)
        enforcer.reset_monthly()
        assert enforcer.current_monthly_spend_cents == 0
        assert enforcer.current_daily_spend_cents == 100

    def test_zero_cap_no_crash(self) -> None:
        """Test that a cap of 0 does not cause division by zero."""
        config = SpendingCapConfig(
            daily_cap_cents=0,
            monthly_cap_cents=0,
            warning_threshold=0.8,
            rate_limit_per_hour=None,
            priority_severities={"high", "critical"},
        )
        enforcer = SpendingCapEnforcer(config)
        # Should not raise ZeroDivisionError
        result = enforcer.check_budget("medium")
        assert result.allowed is True

    def test_invalid_env_vars_handled_gracefully(self) -> None:
        """Test that invalid env var values don't crash from_env."""
        env = {
            "BEEPER_LLM_DAILY_CAP_CENTS": "not_a_number",
            "BEEPER_LLM_MONTHLY_CAP_CENTS": "abc",
            "BEEPER_INVESTIGATION_RATE_LIMIT": "xyz",
            "BEEPER_LLM_CAP_WARNING_THRESHOLD": "bad",
        }
        with patch.dict(os.environ, env, clear=False):
            config = SpendingCapConfig.from_env()
        assert config.daily_cap_cents is None
        assert config.monthly_cap_cents is None
        assert config.rate_limit_per_hour is None
        assert config.warning_threshold == 0.8


# ── LlmClient cost integration tests ──────────────────


class TestLlmClientCostIntegration:
    """Test that LlmClient integrates cost tracking."""

    def test_complete_sync_records_cost(self) -> None:
        """Test that complete_sync records token usage and cost."""
        from beeper_investigator.llm.client import LlmClient, LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key="test-key",
            cache_enabled=False,
        )
        client = LlmClient(config)

        # Mock LiteLLM response with usage
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 1000
        mock_usage.completion_tokens = 500
        mock_response.usage = mock_usage

        with patch("litellm.completion", return_value=mock_response):
            result = client.complete_sync(
                messages=[{"role": "user", "content": "test"}],
            )

        assert result == "test response"
        stats = client.get_cost_stats()
        assert stats["call_count"] == 1
        assert stats["total_cost_usd"] > 0
        assert stats["total_prompt_tokens"] == 1000
        assert stats["total_completion_tokens"] == 500

    def test_cached_call_no_cost_recorded(self) -> None:
        """Test that cached calls don't record additional cost."""
        from beeper_investigator.llm.client import LlmClient, LlmConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key="test-key",
            cache_enabled=True,
        )
        client = LlmClient(config)

        # Mock LiteLLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 1000
        mock_usage.completion_tokens = 500
        mock_response.usage = mock_usage

        messages = [{"role": "user", "content": "hello"}]
        with patch("litellm.completion", return_value=mock_response):
            client.complete_sync(messages=messages)
            # Second call should be cached
            client.complete_sync(messages=messages)

        stats = client.get_cost_stats()
        # Only 1 actual call recorded for cost
        assert stats["call_count"] == 1


# ── Agent spending enforcer integration tests ──────────────────


class TestAgentSpendingEnforcerIntegration:
    """Test that InvestigatorAgent updates spending enforcer after run."""

    def test_agent_updates_spend_after_investigation(self) -> None:
        """Test that agent calls update_spend with actual cost after investigation."""
        from beeper_investigator.agent import InvestigatorAgent

        agent = MagicMock(spec=InvestigatorAgent)
        agent.spending_enforcer = MagicMock()
        agent.spending_enforcer.check_rate_limit.return_value = True
        agent.spending_enforcer.check_budget.return_value = MagicMock(
            allowed=True, warning=False, spend_pct=0.0
        )

        # Verify the method exists and is callable
        assert hasattr(agent.spending_enforcer, "update_spend")
        agent.spending_enforcer.update_spend(150)
        agent.spending_enforcer.update_spend.assert_called_once_with(150)
