"""Tests for Beeper Investigator main module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator import __version__
from beeper_investigator.main import (
    JsonFormatter,
    configure_logging,
    get_required_env,
    main,
)


def test_version() -> None:
    """Test version is set."""
    assert __version__ == "0.1.0"


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_format_basic_log(self) -> None:
        """Test formatting a basic log record."""
        import logging

        formatter = JsonFormatter("test-investigation-123")
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        # Verify it's valid JSON with expected fields
        import json

        data = json.loads(output)
        assert data["investigation_id"] == "test-investigation-123"
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["logger"] == "test_logger"
        assert "timestamp" in data

    def test_format_with_exception(self) -> None:
        """Test formatting a log record with exception info."""
        import json
        import logging

        formatter = JsonFormatter("test-investigation-456")

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test exception" in data["exception"]


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_returns_logger(self) -> None:
        """Test that configure_logging returns a logger."""
        logger = configure_logging("test-inv-001")
        assert logger.name == "beeper_investigator"

    def test_logger_has_json_handler(self) -> None:
        """Test that the logger has a JSON formatter."""
        logger = configure_logging("test-inv-002")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, JsonFormatter)


class TestGetRequiredEnv:
    """Tests for get_required_env function."""

    def test_returns_value_when_set(self) -> None:
        """Test that get_required_env returns the value when set."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert get_required_env("TEST_VAR") == "test_value"

    def test_exits_when_not_set(self) -> None:
        """Test that get_required_env exits when variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the variable if it exists
            os.environ.pop("NONEXISTENT_VAR", None)
            with pytest.raises(SystemExit) as exc_info:
                get_required_env("NONEXISTENT_VAR")
            assert exc_info.value.code == 1

    def test_exits_when_empty(self) -> None:
        """Test that get_required_env exits when variable is empty."""
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            with pytest.raises(SystemExit) as exc_info:
                get_required_env("EMPTY_VAR")
            assert exc_info.value.code == 1


class TestMain:
    """Tests for main function."""

    @pytest.fixture
    def env_vars(self) -> dict[str, str]:
        """Standard environment variables for testing."""
        return {
            "INVESTIGATION_ID": "inv-test-123",
            "INVESTIGATION_NAMESPACE": "default",
            "INVESTIGATION_CONDITION": "High error rate",
            "INVESTIGATION_SERVICE": "payments",
            "INVESTIGATION_SEVERITY": "high",
            "BEEPER_LLM_PROVIDER": "anthropic",
            "BEEPER_LLM_MODEL": "claude-sonnet-4",
            "BEEPER_LLM_API_KEY": "test-api-key",
            "QDRANT_HOST": "localhost",
            "QDRANT_PORT": "6333",
        }

    def test_exits_without_investigation_id(self) -> None:
        """Test that main exits when INVESTIGATION_ID is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_exits_without_investigation_namespace(self) -> None:
        """Test that main exits when INVESTIGATION_NAMESPACE is not set."""
        with patch.dict(
            os.environ, {"INVESTIGATION_ID": "test-inv"}, clear=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_exits_on_llm_client_error(self, env_vars: dict[str, str]) -> None:
        """Test that main exits when LLM client initialization fails."""
        # Remove API key to cause LlmClientError
        env_vars_without_key = {k: v for k, v in env_vars.items() if k != "BEEPER_LLM_API_KEY"}
        with patch.dict(os.environ, env_vars_without_key, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    def test_successful_execution(
        self,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
        env_vars: dict[str, str],
    ) -> None:
        """Test successful investigation execution exits with code 0."""
        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.provider = "anthropic"
        mock_llm.model = "claude-sonnet-4"
        mock_llm.test_connection.return_value = True
        mock_llm_cls.from_env.return_value = mock_llm

        # Mock KB client
        mock_kb = MagicMock()
        mock_kb.health_check.return_value = True
        mock_kb.host = "localhost"
        mock_kb.port = 6333
        mock_kb_cls.return_value = mock_kb

        # Mock status updater
        mock_status = MagicMock()
        mock_status_cls.return_value = mock_status

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        # Verify cleanup was called
        mock_kb.close.assert_called_once()

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    def test_cleanup_on_exception(
        self,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
        env_vars: dict[str, str],
    ) -> None:
        """Test that KB client is closed even on exception."""
        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.provider = "anthropic"
        mock_llm.model = "claude-sonnet-4"
        mock_llm_cls.from_env.return_value = mock_llm

        # Mock KB client that raises exception on health check
        mock_kb = MagicMock()
        mock_kb.health_check.side_effect = RuntimeError("Connection failed")
        mock_kb_cls.return_value = mock_kb

        # Mock status updater
        mock_status = MagicMock()
        mock_status_cls.return_value = mock_status

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        # Verify cleanup was still called
        mock_kb.close.assert_called_once()

    @patch("beeper_investigator.main.InvestigationStatusUpdater")
    @patch("beeper_investigator.main.KBClient")
    @patch("beeper_investigator.main.LlmClient")
    def test_exits_on_agent_failure(
        self,
        mock_llm_cls: MagicMock,
        mock_kb_cls: MagicMock,
        mock_status_cls: MagicMock,
        env_vars: dict[str, str],
    ) -> None:
        """Test that main exits with code 1 when agent fails."""
        mock_llm = MagicMock()
        mock_llm.provider = "anthropic"
        mock_llm.model = "claude-sonnet-4"
        mock_llm.test_connection.return_value = False  # fail LLM check
        mock_llm_cls.from_env.return_value = mock_llm

        mock_kb = MagicMock()
        mock_kb.health_check.return_value = True
        mock_kb_cls.return_value = mock_kb

        mock_status = MagicMock()
        mock_status_cls.return_value = mock_status

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
