"""Tests for LLM retry with exponential backoff."""

from unittest.mock import MagicMock, patch

import litellm
import pytest

from beeper_investigator.llm.retry import (
    RetryConfig,
    retry_with_backoff_async,
    retry_with_backoff_sync,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_defaults(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay_secs == 2.0
        assert config.max_delay_secs == 30.0
        assert config.backoff_factor == 2.0
        assert config.jitter_fraction == 0.25

    def test_from_env_defaults(self) -> None:
        config = RetryConfig.from_env()
        assert config.max_retries == 3
        assert config.base_delay_secs == 2.0
        assert config.max_delay_secs == 30.0

    def test_from_env_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BEEPER_LLM_RETRY_MAX", "5")
        monkeypatch.setenv("BEEPER_LLM_RETRY_BASE_DELAY", "1.0")
        monkeypatch.setenv("BEEPER_LLM_RETRY_MAX_DELAY", "60.0")
        config = RetryConfig.from_env()
        assert config.max_retries == 5
        assert config.base_delay_secs == 1.0
        assert config.max_delay_secs == 60.0

    def test_compute_delay_first_retry(self) -> None:
        config = RetryConfig(jitter_fraction=0.0)
        delay = config.compute_delay(0)
        assert delay == pytest.approx(2.0)

    def test_compute_delay_second_retry(self) -> None:
        config = RetryConfig(jitter_fraction=0.0)
        delay = config.compute_delay(1)
        assert delay == pytest.approx(4.0)

    def test_compute_delay_third_retry(self) -> None:
        config = RetryConfig(jitter_fraction=0.0)
        delay = config.compute_delay(2)
        assert delay == pytest.approx(8.0)

    def test_compute_delay_capped(self) -> None:
        config = RetryConfig(max_delay_secs=10.0, jitter_fraction=0.0)
        delay = config.compute_delay(10)
        assert delay == pytest.approx(10.0)

    def test_compute_delay_jitter_within_bounds(self) -> None:
        config = RetryConfig(jitter_fraction=0.25)
        for _ in range(50):
            delay = config.compute_delay(0)
            # base_delay=2.0 ± 25% → [1.5, 2.5]
            assert 1.5 <= delay <= 2.5

    def test_compute_delay_never_negative(self) -> None:
        config = RetryConfig(base_delay_secs=0.1, jitter_fraction=0.25)
        for _ in range(50):
            delay = config.compute_delay(0)
            assert delay >= 0.0


class TestRetryWithBackoffSync:
    """Tests for synchronous retry logic."""

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_succeeds_first_attempt(self, mock_sleep: MagicMock) -> None:
        func = MagicMock(return_value="ok")
        config = RetryConfig(max_retries=3)
        result = retry_with_backoff_sync(func, config, lambda _: True)
        assert result == "ok"
        func.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_succeeds_after_transient_failure(self, mock_sleep: MagicMock) -> None:
        func = MagicMock(
            side_effect=[
                litellm.exceptions.APIConnectionError("down", "model", "provider"),
                litellm.exceptions.APIConnectionError("down", "model", "provider"),
                "ok",
            ]
        )
        config = RetryConfig(max_retries=3, jitter_fraction=0.0)
        result = retry_with_backoff_sync(func, config, lambda _: True)
        assert result == "ok"
        assert func.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_retry_exhausted_raises(self, mock_sleep: MagicMock) -> None:
        error = litellm.exceptions.APIConnectionError("down", "model", "provider")
        func = MagicMock(side_effect=error)
        config = RetryConfig(max_retries=2, jitter_fraction=0.0)
        with pytest.raises(litellm.exceptions.APIConnectionError):
            retry_with_backoff_sync(func, config, lambda _: True)
        assert func.call_count == 3  # 1 initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_non_retryable_raises_immediately(self, mock_sleep: MagicMock) -> None:
        error = litellm.exceptions.AuthenticationError(
            "bad key", "model", "provider"
        )
        func = MagicMock(side_effect=error)
        config = RetryConfig(max_retries=3)
        with pytest.raises(litellm.exceptions.AuthenticationError):
            def is_retryable(e: Exception) -> bool:
                return not isinstance(e, litellm.exceptions.AuthenticationError)

            retry_with_backoff_sync(func, config, is_retryable)
        func.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_backoff_delays_exponential(self, mock_sleep: MagicMock) -> None:
        error = litellm.exceptions.APIConnectionError("down", "model", "provider")
        func = MagicMock(side_effect=error)
        config = RetryConfig(max_retries=3, jitter_fraction=0.0)
        with pytest.raises(litellm.exceptions.APIConnectionError):
            retry_with_backoff_sync(func, config, lambda _: True)
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == pytest.approx([2.0, 4.0, 8.0])


@pytest.mark.asyncio
class TestRetryWithBackoffAsync:
    """Tests for asynchronous retry logic."""

    @patch("beeper_investigator.llm.retry.asyncio.sleep")
    async def test_succeeds_first_attempt(self, mock_sleep: MagicMock) -> None:
        mock_sleep.return_value = None

        async def func() -> str:
            return "ok"

        config = RetryConfig(max_retries=3)
        result = await retry_with_backoff_async(func, config, lambda _: True)
        assert result == "ok"
        mock_sleep.assert_not_called()

    @patch("beeper_investigator.llm.retry.asyncio.sleep")
    async def test_succeeds_after_transient_failure(self, mock_sleep: MagicMock) -> None:
        mock_sleep.return_value = None
        call_count = 0

        async def func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.exceptions.APIConnectionError("down", "model", "provider")
            return "ok"

        config = RetryConfig(max_retries=3, jitter_fraction=0.0)
        result = await retry_with_backoff_async(func, config, lambda _: True)
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("beeper_investigator.llm.retry.asyncio.sleep")
    async def test_retry_exhausted_raises(self, mock_sleep: MagicMock) -> None:
        mock_sleep.return_value = None

        async def func() -> str:
            raise litellm.exceptions.APIConnectionError("down", "model", "provider")

        config = RetryConfig(max_retries=2, jitter_fraction=0.0)
        with pytest.raises(litellm.exceptions.APIConnectionError):
            await retry_with_backoff_async(func, config, lambda _: True)
