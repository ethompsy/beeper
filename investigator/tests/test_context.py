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

    def test_context_is_immutable(self, full_env: dict[str, str]) -> None:
        """InvestigationContext is frozen (immutable)."""
        with patch.dict(os.environ, full_env, clear=True):
            ctx = InvestigationContext.from_env()

        with pytest.raises(AttributeError):
            ctx.investigation_id = "changed"  # type: ignore[misc]
