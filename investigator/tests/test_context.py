"""Tests for InvestigationContext."""

import os
from unittest.mock import patch

import pytest

from beeper_investigator.context import InvestigationContext


class TestInvestigationContextFromEnv:
    """Tests for InvestigationContext.from_env()."""

    @pytest.fixture
    def full_env(self) -> dict[str, str]:
        """All env vars set."""
        return {
            "INVESTIGATION_ID": "inv-abc-123",
            "INVESTIGATION_NAMESPACE": "production",
            "INVESTIGATION_CONDITION": "High error rate on /api/checkout",
            "INVESTIGATION_SERVICE": "payments",
            "INVESTIGATION_SEVERITY": "high",
        }

    def test_all_env_vars_read(self, full_env: dict[str, str]) -> None:
        """All env vars are correctly read into the context."""
        with patch.dict(os.environ, full_env, clear=True):
            ctx = InvestigationContext.from_env()

        assert ctx.investigation_id == "inv-abc-123"
        assert ctx.namespace == "production"
        assert ctx.condition == "High error rate on /api/checkout"
        assert ctx.service == "payments"
        assert ctx.severity == "high"

    def test_optional_fields_have_defaults(self) -> None:
        """Optional fields default when not set."""
        env = {
            "INVESTIGATION_ID": "inv-minimal",
            "INVESTIGATION_NAMESPACE": "default",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()

        assert ctx.condition == "unknown"
        assert ctx.service == "unknown"
        assert ctx.severity == "medium"

    def test_missing_investigation_id_exits(self) -> None:
        """Missing INVESTIGATION_ID causes SystemExit(1)."""
        env = {"INVESTIGATION_NAMESPACE": "default"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                InvestigationContext.from_env()
            assert exc_info.value.code == 1

    def test_missing_namespace_exits(self) -> None:
        """Missing INVESTIGATION_NAMESPACE causes SystemExit(1)."""
        env = {"INVESTIGATION_ID": "inv-123"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                InvestigationContext.from_env()
            assert exc_info.value.code == 1

    def test_empty_investigation_id_exits(self) -> None:
        """Empty INVESTIGATION_ID causes SystemExit(1)."""
        env = {"INVESTIGATION_ID": "", "INVESTIGATION_NAMESPACE": "default"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                InvestigationContext.from_env()
            assert exc_info.value.code == 1

    def test_trust_level_defaults_to_1(self) -> None:
        """Trust level defaults to 1 (advisory) when not set."""
        env = {
            "INVESTIGATION_ID": "inv-tl",
            "INVESTIGATION_NAMESPACE": "default",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.trust_level == 1

    def test_trust_level_reads_from_env(self) -> None:
        """Trust level reads from INVESTIGATION_TRUST_LEVEL."""
        env = {
            "INVESTIGATION_ID": "inv-tl",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_TRUST_LEVEL": "3",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.trust_level == 3

    def test_trust_level_clamped_to_range(self) -> None:
        """Trust level is clamped between 1 and 5."""
        env = {
            "INVESTIGATION_ID": "inv-tl",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_TRUST_LEVEL": "10",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.trust_level == 5

        env["INVESTIGATION_TRUST_LEVEL"] = "0"
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.trust_level == 1

    def test_trust_level_invalid_defaults_to_1(self) -> None:
        """Invalid trust level value defaults to 1."""
        env = {
            "INVESTIGATION_ID": "inv-tl",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_TRUST_LEVEL": "not_a_number",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.trust_level == 1

    def test_confidence_threshold_defaults_to_0_9(self) -> None:
        """Confidence threshold defaults to 0.9 when not set."""
        env = {
            "INVESTIGATION_ID": "inv-ct",
            "INVESTIGATION_NAMESPACE": "default",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.confidence_threshold == 0.9

    def test_confidence_threshold_reads_from_env(self) -> None:
        """Confidence threshold reads from INVESTIGATION_CONFIDENCE_THRESHOLD."""
        env = {
            "INVESTIGATION_ID": "inv-ct",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_CONFIDENCE_THRESHOLD": "0.85",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.confidence_threshold == 0.85

    def test_confidence_threshold_clamped_to_range(self) -> None:
        """Confidence threshold is clamped between 0.0 and 1.0."""
        env = {
            "INVESTIGATION_ID": "inv-ct",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_CONFIDENCE_THRESHOLD": "1.5",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.confidence_threshold == 1.0

        env["INVESTIGATION_CONFIDENCE_THRESHOLD"] = "-0.5"
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.confidence_threshold == 0.0

    def test_confidence_threshold_invalid_defaults_to_0_9(self) -> None:
        """Invalid confidence threshold defaults to 0.9."""
        env = {
            "INVESTIGATION_ID": "inv-ct",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_CONFIDENCE_THRESHOLD": "abc",
        }
        with patch.dict(os.environ, env, clear=True):
            ctx = InvestigationContext.from_env()
        assert ctx.confidence_threshold == 0.9

    def test_context_is_immutable(self, full_env: dict[str, str]) -> None:
        """InvestigationContext is frozen (immutable)."""
        with patch.dict(os.environ, full_env, clear=True):
            ctx = InvestigationContext.from_env()

        with pytest.raises(AttributeError):
            ctx.investigation_id = "changed"  # type: ignore[misc]
