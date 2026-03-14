"""Tests for the LLM client module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from beeper_investigator.llm import LlmClient, LlmClientError, LlmConfig


class TestLlmConfig:
    """Tests for LlmConfig."""

    def test_from_env_valid_anthropic(self) -> None:
        """Test creating config from env with valid Anthropic settings."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.provider == "anthropic"
            assert config.model == "claude-sonnet-4"
            assert config.api_key == "test-key"
            assert config.endpoint is None

    def test_from_env_valid_openai(self) -> None:
        """Test creating config from env with valid OpenAI settings."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "openai",
                "BEEPER_LLM_MODEL": "gpt-4o",
                "BEEPER_LLM_API_KEY": "sk-test",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.provider == "openai"
            assert config.model == "gpt-4o"
            assert config.api_key == "sk-test"

    def test_from_env_valid_azure(self) -> None:
        """Test creating config from env with valid Azure settings."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "azure",
                "BEEPER_LLM_MODEL": "my-deployment",
                "BEEPER_LLM_API_KEY": "azure-key",
                "BEEPER_LLM_ENDPOINT": "https://my-resource.openai.azure.com",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.provider == "azure"
            assert config.model == "my-deployment"
            assert config.endpoint == "https://my-resource.openai.azure.com"

    def test_from_env_valid_ollama(self) -> None:
        """Test creating config from env with valid Ollama settings (no API key)."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "ollama",
                "BEEPER_LLM_MODEL": "llama3",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.provider == "ollama"
            assert config.model == "llama3"
            assert config.api_key is None

    def test_from_env_missing_provider(self) -> None:
        """Test error when provider is missing."""
        with patch.dict(os.environ, {"BEEPER_LLM_MODEL": "claude-sonnet-4"}, clear=True):
            with pytest.raises(LlmClientError, match="BEEPER_LLM_PROVIDER.*required"):
                LlmConfig.from_env()

    def test_from_env_missing_model(self) -> None:
        """Test error when model is missing."""
        with patch.dict(os.environ, {"BEEPER_LLM_PROVIDER": "anthropic"}, clear=True):
            with pytest.raises(LlmClientError, match="BEEPER_LLM_MODEL.*required"):
                LlmConfig.from_env()

    def test_from_env_invalid_provider(self) -> None:
        """Test error when provider is invalid."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "invalid",
                "BEEPER_LLM_MODEL": "model",
            },
            clear=True,
        ):
            with pytest.raises(LlmClientError, match="Invalid provider 'invalid'"):
                LlmConfig.from_env()

    def test_from_env_anthropic_missing_api_key(self) -> None:
        """Test error when Anthropic provider is missing API key."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
            },
            clear=True,
        ):
            with pytest.raises(LlmClientError, match="BEEPER_LLM_API_KEY is required"):
                LlmConfig.from_env()

    def test_from_env_azure_missing_endpoint(self) -> None:
        """Test error when Azure provider is missing endpoint."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "azure",
                "BEEPER_LLM_MODEL": "deployment",
                "BEEPER_LLM_API_KEY": "key",
            },
            clear=True,
        ):
            with pytest.raises(LlmClientError, match="BEEPER_LLM_ENDPOINT is required"):
                LlmConfig.from_env()

    def test_get_litellm_model_anthropic(self) -> None:
        """Test LiteLLM model string for Anthropic."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        assert config.get_litellm_model() == "claude-sonnet-4"

    def test_get_litellm_model_azure(self) -> None:
        """Test LiteLLM model string for Azure (adds prefix)."""
        config = LlmConfig(
            provider="azure",
            model="my-deployment",
            api_key="key",
            endpoint="https://test.openai.azure.com",
        )
        assert config.get_litellm_model() == "azure/my-deployment"

    def test_get_litellm_model_azure_already_prefixed(self) -> None:
        """Test LiteLLM model string for Azure when already prefixed."""
        config = LlmConfig(
            provider="azure",
            model="azure/my-deployment",
            api_key="key",
            endpoint="https://test.openai.azure.com",
        )
        assert config.get_litellm_model() == "azure/my-deployment"

    def test_get_litellm_model_ollama(self) -> None:
        """Test LiteLLM model string for Ollama (adds prefix)."""
        config = LlmConfig(provider="ollama", model="llama3")
        assert config.get_litellm_model() == "ollama/llama3"

    def test_validate_model_anthropic_valid(self) -> None:
        """Test model validation passes for valid Anthropic model."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        config.validate_model()  # Should not raise

    def test_validate_model_anthropic_invalid(self) -> None:
        """Test model validation fails for invalid Anthropic model."""
        config = LlmConfig(provider="anthropic", model="gpt-4", api_key="key")
        with pytest.raises(LlmClientError, match="Invalid model.*Anthropic"):
            config.validate_model()

    def test_validate_model_openai_valid(self) -> None:
        """Test model validation passes for valid OpenAI model."""
        config = LlmConfig(provider="openai", model="gpt-4o", api_key="key")
        config.validate_model()  # Should not raise

    def test_validate_model_openai_invalid(self) -> None:
        """Test model validation fails for invalid OpenAI model."""
        config = LlmConfig(provider="openai", model="claude-3", api_key="key")
        with pytest.raises(LlmClientError, match="Invalid model.*OpenAI"):
            config.validate_model()

    def test_validate_model_empty(self) -> None:
        """Test model validation fails for empty model."""
        config = LlmConfig(provider="anthropic", model="", api_key="key")
        with pytest.raises(LlmClientError, match="Model name cannot be empty"):
            config.validate_model()

    def test_from_env_validates_model(self) -> None:
        """Test that from_env validates the model name."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "gpt-4",  # Invalid for Anthropic
                "BEEPER_LLM_API_KEY": "test-key",
            },
            clear=True,
        ):
            with pytest.raises(LlmClientError, match="Invalid model"):
                LlmConfig.from_env()


class TestLlmClient:
    """Tests for LlmClient."""

    def test_client_creation(self) -> None:
        """Test creating an LLM client."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)
        assert client.provider == "anthropic"
        assert client.model == "claude-sonnet-4"

    def test_from_env(self) -> None:
        """Test creating client from environment."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "test-key",
            },
            clear=True,
        ):
            client = LlmClient.from_env()
            assert client.provider == "anthropic"
            assert client.model == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_complete_success(self) -> None:
        """Test successful completion request."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response
            result = await client.complete(
                messages=[{"role": "user", "content": "Hello"}]
            )
            assert result == "Test response"
            mock_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_auth_error(self) -> None:
        """Test completion with authentication error."""
        import litellm.exceptions

        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="bad-key")
        client = LlmClient(config)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = litellm.exceptions.AuthenticationError(
                message="Invalid API key",
                llm_provider="anthropic",
                model="claude-sonnet-4",
            )
            with pytest.raises(LlmClientError, match="Authentication failed"):
                await client.complete(messages=[{"role": "user", "content": "Hello"}])

    @pytest.mark.asyncio
    async def test_complete_rate_limit_error(self) -> None:
        """Test completion with rate limit error."""
        import litellm.exceptions

        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = litellm.exceptions.RateLimitError(
                message="Rate limited",
                llm_provider="anthropic",
                model="claude-sonnet-4",
            )
            with pytest.raises(LlmClientError, match="Rate limited"):
                await client.complete(messages=[{"role": "user", "content": "Hello"}])

    @pytest.mark.asyncio
    async def test_complete_connection_error(self) -> None:
        """Test completion with connection error."""
        import litellm.exceptions

        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = litellm.exceptions.APIConnectionError(
                message="Connection failed",
                llm_provider="anthropic",
                model="claude-sonnet-4",
            )
            with pytest.raises(LlmClientError, match="Cannot reach LLM provider"):
                await client.complete(messages=[{"role": "user", "content": "Hello"}])

    def test_complete_sync_success(self) -> None:
        """Test successful synchronous completion request."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sync response"

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = mock_response
            result = client.complete_sync(
                messages=[{"role": "user", "content": "Hello"}]
            )
            assert result == "Sync response"

    @pytest.mark.asyncio
    async def test_test_connection_success(self) -> None:
        """Test successful connection test."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response
            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self) -> None:
        """Test failed connection test."""
        import litellm.exceptions

        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="bad-key")
        client = LlmClient(config)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = litellm.exceptions.AuthenticationError(
                message="Invalid API key",
                llm_provider="anthropic",
                model="claude-sonnet-4",
            )
            with pytest.raises(LlmClientError, match="Authentication failed"):
                await client.test_connection()


class TestLlmClientRetry:
    """Tests for retry integration in LlmClient."""

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_complete_sync_retries_on_connection_error(self, mock_sleep: MagicMock) -> None:
        """Test that complete_sync retries on transient connection errors."""
        import litellm.exceptions

        from beeper_investigator.llm.retry import RetryConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            retry_config=RetryConfig(max_retries=2, jitter_fraction=0.0),
        )
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage = None

        with patch("litellm.completion") as mock_completion:
            mock_completion.side_effect = [
                litellm.exceptions.APIConnectionError("down", "model", "provider"),
                mock_response,
            ]
            result = client.complete_sync(
                messages=[{"role": "user", "content": "test"}],
            )

        assert result == "ok"
        assert mock_completion.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_complete_sync_no_retry_on_auth_error(self, mock_sleep: MagicMock) -> None:
        """Test that AuthenticationError is not retried."""
        import litellm.exceptions

        from beeper_investigator.llm.retry import RetryConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            retry_config=RetryConfig(max_retries=3, jitter_fraction=0.0),
        )
        client = LlmClient(config)

        with patch("litellm.completion") as mock_completion:
            mock_completion.side_effect = litellm.exceptions.AuthenticationError(
                "bad key", "model", "provider"
            )
            with pytest.raises(LlmClientError, match="Authentication failed"):
                client.complete_sync(
                    messages=[{"role": "user", "content": "test"}],
                )

        assert mock_completion.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch("beeper_investigator.llm.retry.asyncio.sleep")
    async def test_complete_retries_on_connection_error(self, mock_sleep: MagicMock) -> None:
        """Test that async complete() retries on transient errors."""
        import litellm.exceptions

        from beeper_investigator.llm.retry import RetryConfig

        mock_sleep.return_value = None

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            retry_config=RetryConfig(max_retries=2, jitter_fraction=0.0),
        )
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = [
                litellm.exceptions.APIConnectionError("down", "model", "provider"),
                mock_response,
            ]
            result = await client.complete(
                messages=[{"role": "user", "content": "test"}],
            )

        assert result == "ok"
        assert mock_completion.call_count == 2

    @patch("beeper_investigator.llm.retry.time.sleep")
    def test_embed_sync_retries_on_connection_error(self, mock_sleep: MagicMock) -> None:
        """Test that embed_sync retries on transient errors."""
        import litellm.exceptions

        from beeper_investigator.llm.retry import RetryConfig

        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="test-key",
            embedding_model="text-embedding-ada-002",
            retry_config=RetryConfig(max_retries=2, jitter_fraction=0.0),
        )
        client = LlmClient(config)

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        with patch("litellm.embedding") as mock_embedding:
            mock_embedding.side_effect = [
                litellm.exceptions.APIConnectionError("down", "model", "provider"),
                mock_response,
            ]
            result = client.embed_sync("test text")

        assert result == [0.1, 0.2, 0.3]
        assert mock_embedding.call_count == 2
        assert mock_sleep.call_count == 1


class TestIsRetryable:
    """Tests for is_retryable() exception classification."""

    def test_connection_error_is_retryable(self) -> None:
        import litellm.exceptions

        from beeper_investigator.llm.client import is_retryable

        err = litellm.exceptions.APIConnectionError("down", "model", "provider")
        assert is_retryable(err) is True

    def test_rate_limit_is_retryable(self) -> None:
        import litellm.exceptions

        from beeper_investigator.llm.client import is_retryable

        err = litellm.exceptions.RateLimitError("limited", "model", "provider")
        assert is_retryable(err) is True

    def test_auth_error_not_retryable(self) -> None:
        import litellm.exceptions

        from beeper_investigator.llm.client import is_retryable

        err = litellm.exceptions.AuthenticationError("bad key", "model", "provider")
        assert is_retryable(err) is False

    def test_bad_request_not_retryable(self) -> None:
        import litellm.exceptions

        from beeper_investigator.llm.client import is_retryable

        err = litellm.exceptions.BadRequestError("invalid", "model", "provider")
        assert is_retryable(err) is False

    def test_non_litellm_exception_not_retryable(self) -> None:
        """Programming errors should not be retried."""
        from beeper_investigator.llm.client import is_retryable

        assert is_retryable(TypeError("unexpected type")) is False
        assert is_retryable(KeyError("missing key")) is False
        assert is_retryable(ValueError("bad value")) is False

