"""Tests for LLM embedding model support."""

import os
from unittest.mock import MagicMock, patch

from beeper_investigator.llm.client import LlmClient, LlmClientError, LlmConfig

import pytest


class TestLlmConfigEmbeddingModel:
    """Tests for embedding_model in LlmConfig."""

    def test_embedding_model_from_env(self) -> None:
        """BEEPER_LLM_EMBEDDING_MODEL is read from env."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_EMBEDDING_MODEL": "text-embedding-3-small",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.embedding_model == "text-embedding-3-small"

    def test_embedding_model_defaults_none(self) -> None:
        """embedding_model defaults to None when env var not set."""
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
            assert config.embedding_model is None

    def test_embedding_model_empty_string_becomes_none(self) -> None:
        """Empty BEEPER_LLM_EMBEDDING_MODEL becomes None."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_EMBEDDING_MODEL": "",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.embedding_model is None


class TestEmbedSync:
    """Tests for LlmClient.embed_sync()."""

    def test_embed_sync_returns_vector(self) -> None:
        """embed_sync() returns embedding vector from litellm."""
        config = LlmConfig(
            provider="openai",
            model="gpt-4",
            api_key="key",
            embedding_model="text-embedding-3-small",
        )
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        with patch("litellm.embedding") as mock_embed:
            mock_embed.return_value = mock_response
            result = client.embed_sync("test text")

        assert result == [0.1, 0.2, 0.3]
        mock_embed.assert_called_once_with(
            model="text-embedding-3-small",
            input=["test text"],
        )

    def test_embed_sync_raises_when_not_configured(self) -> None:
        """embed_sync() raises LlmClientError when embedding model not set."""
        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="key",
        )
        client = LlmClient(config)

        with pytest.raises(LlmClientError, match="Embedding model not configured"):
            client.embed_sync("test text")

    def test_embed_sync_wraps_litellm_error(self) -> None:
        """embed_sync() wraps litellm exceptions into LlmClientError."""
        config = LlmConfig(
            provider="openai",
            model="gpt-4",
            api_key="key",
            embedding_model="text-embedding-3-small",
        )
        client = LlmClient(config)

        with patch("litellm.embedding") as mock_embed:
            mock_embed.side_effect = Exception("API error")
            with pytest.raises(LlmClientError, match="LLM request failed"):
                client.embed_sync("test text")

    def test_embed_sync_uses_configured_model(self) -> None:
        """embed_sync() uses the configured embedding model."""
        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="key",
            embedding_model="ollama/nomic-embed-text",
        )
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [1.0]}]

        with patch("litellm.embedding") as mock_embed:
            mock_embed.return_value = mock_response
            client.embed_sync("query")

        assert mock_embed.call_args[1]["model"] == "ollama/nomic-embed-text"
