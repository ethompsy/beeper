"""Spending cap and rate limiting enforcement for LLM usage.

Provides configuration-driven spending caps (daily/monthly) and rate limiting
for investigations. Enforcement is optional — disabled when env vars are not set.
"""

import logging
import os
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CapCheckResult:
    """Result of a spending cap or rate limit check."""

    allowed: bool
    reason: str
    warning: bool = False
    spend_pct: float = 0.0


@dataclass
class SpendingCapConfig:
    """Configuration for spending caps and rate limiting."""

    daily_cap_cents: int | None
    monthly_cap_cents: int | None
    warning_threshold: float
    rate_limit_per_hour: int | None
    priority_severities: set[str]

    @property
    def enabled(self) -> bool:
        """True if any cap or rate limit is configured."""
        return (
            self.daily_cap_cents is not None
            or self.monthly_cap_cents is not None
            or self.rate_limit_per_hour is not None
        )

    @classmethod
    def from_env(cls) -> "SpendingCapConfig":
        """Load spending cap config from environment variables.

        Environment variables:
            BEEPER_LLM_DAILY_CAP_CENTS: Daily spending cap in cents (e.g., 5000 = $50)
            BEEPER_LLM_MONTHLY_CAP_CENTS: Monthly spending cap in cents
            BEEPER_LLM_CAP_WARNING_THRESHOLD: Warning threshold ratio (default 0.8)
            BEEPER_INVESTIGATION_RATE_LIMIT: Max investigations per hour
            BEEPER_CAP_PRIORITY_SEVERITIES: Comma-separated severity list (default high,critical)
        """
        daily_raw = os.environ.get("BEEPER_LLM_DAILY_CAP_CENTS")
        monthly_raw = os.environ.get("BEEPER_LLM_MONTHLY_CAP_CENTS")
        rate_raw = os.environ.get("BEEPER_INVESTIGATION_RATE_LIMIT")
        threshold_raw = os.environ.get("BEEPER_LLM_CAP_WARNING_THRESHOLD", "0.8")
        priorities_raw = os.environ.get(
            "BEEPER_CAP_PRIORITY_SEVERITIES", "high,critical"
        )

        daily_cap = int(daily_raw) if daily_raw else None
        monthly_cap = int(monthly_raw) if monthly_raw else None
        rate_limit = int(rate_raw) if rate_raw else None
        warning_threshold = float(threshold_raw)
        priority_severities = {
            s.strip() for s in priorities_raw.split(",") if s.strip()
        }

        return cls(
            daily_cap_cents=daily_cap,
            monthly_cap_cents=monthly_cap,
            warning_threshold=warning_threshold,
            rate_limit_per_hour=rate_limit,
            priority_severities=priority_severities,
        )


class SpendingCapEnforcer:
    """Enforces spending caps and rate limits for investigations.

    Tracks cumulative spend and investigation rate in-memory.
    Scoped to the pod lifecycle (resets on restart).
    """

    def __init__(self, config: SpendingCapConfig) -> None:
        self.config = config
        self._current_daily_spend_cents: int = 0
        self._current_monthly_spend_cents: int = 0
        self._investigation_timestamps: deque[float] = deque()

    def update_spend(self, cost_cents: int) -> None:
        """Record additional spend.

        Args:
            cost_cents: Cost in cents to add to current tracking.
        """
        self._current_daily_spend_cents += cost_cents
        self._current_monthly_spend_cents += cost_cents

    def check_budget(self, severity: str) -> CapCheckResult:
        """Check if an investigation is allowed under current spending caps.

        Args:
            severity: Investigation severity level (e.g., 'critical', 'high').

        Returns:
            CapCheckResult with allowed/denied status and reason.
        """
        is_priority = severity.lower() in self.config.priority_severities

        # Check daily cap
        if self.config.daily_cap_cents is not None:
            daily_pct = self._current_daily_spend_cents / self.config.daily_cap_cents
            if daily_pct >= 1.0 and not is_priority:
                return CapCheckResult(
                    allowed=False,
                    reason=(
                        f"Daily spending cap reached "
                        f"({self._current_daily_spend_cents}/{self.config.daily_cap_cents} cents)"
                    ),
                    warning=False,
                    spend_pct=daily_pct * 100,
                )
            if daily_pct >= self.config.warning_threshold:
                logger.warning(
                    "Daily spending at %.1f%% of cap (%d/%d cents)",
                    daily_pct * 100,
                    self._current_daily_spend_cents,
                    self.config.daily_cap_cents,
                )
                if daily_pct < 1.0:
                    return CapCheckResult(
                        allowed=True,
                        reason=f"Daily spend at {daily_pct:.0%} of cap",
                        warning=True,
                        spend_pct=daily_pct * 100,
                    )

        # Check monthly cap
        if self.config.monthly_cap_cents is not None:
            monthly_pct = (
                self._current_monthly_spend_cents / self.config.monthly_cap_cents
            )
            if monthly_pct >= 1.0 and not is_priority:
                return CapCheckResult(
                    allowed=False,
                    reason=(
                        f"Monthly spending cap reached "
                        f"({self._current_monthly_spend_cents}"
                        f"/{self.config.monthly_cap_cents} cents)"
                    ),
                    warning=False,
                    spend_pct=monthly_pct * 100,
                )
            if monthly_pct >= self.config.warning_threshold:
                logger.warning(
                    "Monthly spending at %.1f%% of cap (%d/%d cents)",
                    monthly_pct * 100,
                    self._current_monthly_spend_cents,
                    self.config.monthly_cap_cents,
                )
                if monthly_pct < 1.0:
                    return CapCheckResult(
                        allowed=True,
                        reason=f"Monthly spend at {monthly_pct:.0%} of cap",
                        warning=True,
                        spend_pct=monthly_pct * 100,
                    )

        return CapCheckResult(
            allowed=True,
            reason="Within budget",
            warning=False,
            spend_pct=0.0,
        )

    def check_rate_limit(self) -> bool:
        """Check if investigation rate is within configured limits.

        Uses a sliding window to count investigations in the last hour.

        Returns:
            True if within rate limit, False if rate exceeded.
        """
        if self.config.rate_limit_per_hour is None:
            return True

        now = time.monotonic()
        window_seconds = 3600.0

        # Evict timestamps older than the window
        while (
            self._investigation_timestamps
            and now - self._investigation_timestamps[0] > window_seconds
        ):
            self._investigation_timestamps.popleft()

        return len(self._investigation_timestamps) < self.config.rate_limit_per_hour

    def record_investigation(self) -> None:
        """Record an investigation timestamp for rate limiting."""
        self._investigation_timestamps.append(time.monotonic())

    @property
    def current_daily_spend_cents(self) -> int:
        """Current daily spend in cents."""
        return self._current_daily_spend_cents

    @property
    def current_monthly_spend_cents(self) -> int:
        """Current monthly spend in cents."""
        return self._current_monthly_spend_cents

    @property
    def investigations_in_window(self) -> int:
        """Number of investigations in the current rate limit window."""
        now = time.monotonic()
        while (
            self._investigation_timestamps
            and now - self._investigation_timestamps[0] > 3600.0
        ):
            self._investigation_timestamps.popleft()
        return len(self._investigation_timestamps)

    def reset_daily(self) -> None:
        """Reset daily spend counter."""
        self._current_daily_spend_cents = 0

    def reset_monthly(self) -> None:
        """Reset monthly spend counter."""
        self._current_monthly_spend_cents = 0
