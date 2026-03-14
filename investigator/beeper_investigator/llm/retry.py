"""Retry with exponential backoff for LLM calls.

Provides configurable retry logic with exponential backoff and jitter
for transient LLM provider failures (connection errors, rate limits).
"""

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay_secs: float = 2.0
    max_delay_secs: float = 30.0
    backoff_factor: float = 2.0
    jitter_fraction: float = 0.25

    @classmethod
    def from_env(cls) -> "RetryConfig":
        """Create RetryConfig from environment variables.

        Environment variables:
            BEEPER_LLM_RETRY_MAX: Maximum retry attempts (default 3)
            BEEPER_LLM_RETRY_BASE_DELAY: Base delay in seconds (default 2.0)
            BEEPER_LLM_RETRY_MAX_DELAY: Maximum delay in seconds (default 30.0)

        Returns:
            RetryConfig instance.
        """
        return cls(
            max_retries=int(os.environ.get("BEEPER_LLM_RETRY_MAX", "3")),
            base_delay_secs=float(os.environ.get("BEEPER_LLM_RETRY_BASE_DELAY", "2.0")),
            max_delay_secs=float(os.environ.get("BEEPER_LLM_RETRY_MAX_DELAY", "30.0")),
        )

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for a given retry attempt with jitter.

        Args:
            attempt: Zero-based attempt number (0 = first retry).

        Returns:
            Delay in seconds with jitter applied.
        """
        delay = min(
            self.base_delay_secs * (self.backoff_factor ** attempt),
            self.max_delay_secs,
        )
        jitter = delay * self.jitter_fraction * (2 * random.random() - 1)
        return max(0.0, delay + jitter)


def retry_with_backoff_sync(
    func: Callable[..., T],
    config: RetryConfig,
    is_retryable: Callable[[Exception], bool],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute a synchronous function with retry and exponential backoff.

    Args:
        func: The function to call.
        config: Retry configuration.
        is_retryable: Classifier that returns True for retryable exceptions.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func.

    Raises:
        Exception: The last exception if all retries are exhausted,
            or immediately if the exception is non-retryable.
    """
    last_exception: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if not is_retryable(e):
                logger.warning(
                    "Non-retryable error on attempt %d/%d: %s",
                    attempt + 1,
                    config.max_retries + 1,
                    e,
                )
                raise
            if attempt < config.max_retries:
                delay = config.compute_delay(attempt)
                logger.warning(
                    "Retryable error on attempt %d/%d, retrying in %.1fs: %s",
                    attempt + 1,
                    config.max_retries + 1,
                    delay,
                    e,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempts exhausted: %s",
                    config.max_retries + 1,
                    e,
                )
    raise last_exception  # type: ignore[misc]


async def retry_with_backoff_async(
    func: Callable[..., Any],
    config: RetryConfig,
    is_retryable: Callable[[Exception], bool],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry and exponential backoff.

    Args:
        func: The async function to call.
        config: Retry configuration.
        is_retryable: Classifier that returns True for retryable exceptions.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func.

    Raises:
        Exception: The last exception if all retries are exhausted,
            or immediately if the exception is non-retryable.
    """
    last_exception: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if not is_retryable(e):
                logger.warning(
                    "Non-retryable error on attempt %d/%d: %s",
                    attempt + 1,
                    config.max_retries + 1,
                    e,
                )
                raise
            if attempt < config.max_retries:
                delay = config.compute_delay(attempt)
                logger.warning(
                    "Retryable error on attempt %d/%d, retrying in %.1fs: %s",
                    attempt + 1,
                    config.max_retries + 1,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %d attempts exhausted: %s",
                    config.max_retries + 1,
                    e,
                )
    raise last_exception  # type: ignore[misc]
