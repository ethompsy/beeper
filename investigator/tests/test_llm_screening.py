"""Tests for LLM model override and screening model support."""

import os
from unittest.mock import MagicMock, patch

from beeper_investigator.llm.client import LlmClient, LlmConfig


class TestLlmConfigScreeningModel:
    """Tests for screening_model in LlmConfig."""

    def test_screening_model_from_env(self) -> None:
        """BEEPER_LLM_SCREENING_MODEL is read from env."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_SCREENING_MODEL": "claude-3-haiku-20240307",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.screening_model == "claude-3-haiku-20240307"

    def test_screening_model_defaults_none(self) -> None:
        """screening_model defaults to None when env var not set."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.screening_model is None


class TestLlmClientScreeningModel:
    """Tests for screening_model property on LlmClient."""

    def test_screening_model_returns_configured(self) -> None:
        """screening_model returns the configured screening model."""
        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="key",
            screening_model="claude-3-haiku-20240307",
        )
        client = LlmClient(config)
        assert client.screening_model == "anthropic/claude-3-haiku-20240307"

    def test_screening_model_falls_back_to_default(self) -> None:
        """screening_model falls back to default model when not configured."""
        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="key",
        )
        client = LlmClient(config)
        assert client.screening_model == "anthropic/claude-sonnet-4"

    def test_screening_model_fallback_uses_litellm_format(self) -> None:
        """screening_model fallback applies provider prefix for Azure/Ollama."""
        config = LlmConfig(
            provider="azure",
            model="my-deployment",
            api_key="key",
            endpoint="https://my.azure.endpoint",
        )
        client = LlmClient(config)
        # Should get azure/ prefix, not raw model name
        assert client.screening_model == "azure/my-deployment"


class TestCompleteSyncModelOverride:
    """Tests for model override in complete_sync()."""

    def test_model_override_used(self) -> None:
        """complete_sync() uses model override when provided."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = mock_response
            client.complete_sync(
                messages=[{"role": "user", "content": "test"}],
                model="claude-3-haiku-20240307",
            )

            call_kwargs = mock_completion.call_args
            assert call_kwargs[1]["model"] == "claude-3-haiku-20240307"

    def test_default_model_when_no_override(self) -> None:
        """complete_sync() uses default model when no override."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = mock_response
            client.complete_sync(messages=[{"role": "user", "content": "test"}])

            call_kwargs = mock_completion.call_args
            assert call_kwargs[1]["model"] == "anthropic/claude-sonnet-4"
