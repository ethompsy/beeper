"""Tests for Task 5.3 — Source connection status & LLM spending views.

One named test per acceptance criterion:

- AC1 (FR34): Observe > Sources shows Prometheus/Loki connection status with
  indicators.
- AC2:        Connected → green "Connected" + last-seen; disconnected/error →
  red "Disconnected".
- AC3 (FR35): Manage > Spending shows LLM provider config + spending metrics.
- AC4 (NFR12): After a simulated operator restart, the Sources view renders a
  consistent, duplicate-free list (UI-layer surface of the operator's
  idempotent CRD resume guarantee).

These follow the project test convention (render assertions via the Flask test
client; no JS runner). Source data is mocked at the operator HTTP boundary with
respx; spending provider config is exercised through the SpendingService and
the spending route template.

Task 6.3 (D13/D14) retired the Jinja `/sources/` and `/spending/` full-page +
HTMX-partial routes (`sources/list.html`, `sources/_list_content.html`,
`spending/spending.html`, `spending/_spending_content.html` all deleted); both
bare URLs now 302-redirect to their React equivalents
(`/app/sources`, `/app/spending`). AC1, AC2, and the `/spending/`-rendering
half of AC3 tested that now-deleted HTML — those tests have been removed.

AC4's dedup-by-name assertions (`/sources/` rendering) have also been removed,
but the underlying coverage is NOT lost: `test_api_v1_sources_spending.py`'s
`TestSourcesListEndpoint::test_dedup_by_name_preserved` exercises the exact
same `SourceService.get_sources()` dedup-by-name logic through the JSON API
endpoint (`/api/v1/sources/`), which the Jinja route never duplicated logic
for.
"""

from unittest.mock import patch

from beeper_ui.services.spending_service import SpendingService

# ── AC3 ──────────────────────────────────────────────────────────────────────


class TestAC3SpendingProviderConfigAndMetrics:
    """AC3 (FR35): Spending shows LLM provider config + spending metrics.

    Only `SpendingService.get_provider_config()` is tested here now — the
    `/spending/` route-level render assertion (provider config + spend
    metrics appearing in the retired `spending.html`) was removed under
    Task 6.3 (see module docstring).
    """

    def test_ac3_provider_config_masks_api_key_and_reads_env(self) -> None:
        """get_provider_config surfaces provider/model and masks the API key."""
        svc = SpendingService()
        with patch.dict(
            "os.environ",
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "sk-secret-abcd1234",
                "BEEPER_LLM_DAILY_CAP_CENTS": "5000",
            },
            clear=False,
        ):
            cfg = svc.get_provider_config()

        assert cfg["configured"] is True
        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-sonnet-4"
        assert cfg["daily_cap_usd"] == 50.0
        # API key is masked — never returned in full.
        assert cfg["api_key_configured"] is True
        assert cfg["api_key_masked"] == "••••••1234"
        assert "sk-secret-abcd1234" not in str(cfg["api_key_masked"])
