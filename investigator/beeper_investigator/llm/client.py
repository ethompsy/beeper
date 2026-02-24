"""LLM client wrapper using LiteLLM for provider flexibility.

This module provides a unified interface to multiple LLM providers through LiteLLM.
Configuration is loaded from environment variables:
- BEEPER_LLM_PROVIDER: Provider name (anthropic, openai, azure, ollama)
- BEEPER_LLM_MODEL: Model identifier
- BEEPER_LLM_API_KEY: API key (not needed for Ollama)
- BEEPER_LLM_ENDPOINT: Custom endpoint (optional, required for Azure)
"""

import os
from dataclasses import dataclass
from typing import Any

import litellm


@dataclass
class LlmConfig:
    """Configuration for the LLM client."""

    provider: str
    model: str
    api_key: str | None = None
    endpoint: str | None = None
    screening_model: str | None = None

    def validate_model(self) -> None:
        """Validate the model name format for the configured provider.

        Raises:
            LlmClientError: If the model name is invalid for the provider.
        """
        if not self.model:
            raise LlmClientError("Model name cannot be empty")

        if self.provider == "anthropic":
            if not self.model.startswith("claude"):
                raise LlmClientError(
                    f"Invalid model '{self.model}' for Anthropic: must start with 'claude'"
                )
        elif self.provider == "openai":
            valid_prefixes = ("gpt-", "o1", "chatgpt")
            if not any(self.model.startswith(p) for p in valid_prefixes):
                raise LlmClientError(
                    f"Invalid model '{self.model}' for OpenAI: "
                    "must start with 'gpt-', 'o1', or 'chatgpt'"
                )
        # Azure and Ollama accept any model name (deployment names / local models)

    @classmethod
    def from_env(cls) -> "LlmConfig":
        """Create LlmConfig from environment variables.

        Environment variables:
            BEEPER_LLM_PROVIDER: Provider name (anthropic, openai, azure, ollama)
            BEEPER_LLM_MODEL: Model identifier
            BEEPER_LLM_API_KEY: API key (optional for ollama)
            BEEPER_LLM_ENDPOINT: Custom endpoint (optional)

        Returns:
            LlmConfig instance

        Raises:
            LlmClientError: If required environment variables are missing.
        """
        provider = os.environ.get("BEEPER_LLM_PROVIDER", "").lower()
        model = os.environ.get("BEEPER_LLM_MODEL", "")
        api_key = os.environ.get("BEEPER_LLM_API_KEY")
        endpoint = os.environ.get("BEEPER_LLM_ENDPOINT")
        screening_model = os.environ.get("BEEPER_LLM_SCREENING_MODEL") or None

        if not provider:
            raise LlmClientError("BEEPER_LLM_PROVIDER environment variable is required")
        if not model:
            raise LlmClientError("BEEPER_LLM_MODEL environment variable is required")

        # Validate provider
        valid_providers = {"anthropic", "openai", "azure", "ollama"}
        if provider not in valid_providers:
            valid_str = ", ".join(sorted(valid_providers))
            raise LlmClientError(
                f"Invalid provider '{provider}'. Must be one of: {valid_str}"
            )

        # Cloud providers require API key
        if provider in {"anthropic", "openai", "azure"} and not api_key:
            raise LlmClientError(
                f"BEEPER_LLM_API_KEY is required for provider '{provider}'"
            )

        # Azure requires endpoint
        if provider == "azure" and not endpoint:
            raise LlmClientError("BEEPER_LLM_ENDPOINT is required for Azure provider")

        config = cls(
            provider=provider,
            model=model,
            api_key=api_key,
            endpoint=endpoint,
            screening_model=screening_model,
        )
        config.validate_model()
        return config

    def get_litellm_model(self) -> str:
        """Get the model string formatted for LiteLLM.

        LiteLLM expects provider-prefixed model names for some providers.

        Returns:
            Model string formatted for LiteLLM.
        """
        # Azure and Ollama need provider prefix
        if self.provider == "azure":
            # Azure format: azure/<deployment-name>
            if not self.model.startswith("azure/"):
                return f"azure/{self.model}"
        elif self.provider == "ollama":
            # Ollama format: ollama/<model-name>
            if not self.model.startswith("ollama/"):
                return f"ollama/{self.model}"
        # Anthropic and OpenAI work with raw model names
        return self.model


class LlmClientError(Exception):
    """Error from the LLM client."""

    pass


def _handle_litellm_error(e: Exception) -> LlmClientError:
    """Convert LiteLLM exceptions to LlmClientError with user-friendly messages."""
    if isinstance(e, litellm.exceptions.AuthenticationError):
        return LlmClientError(f"Authentication failed: check API key is valid. {e}")
    elif isinstance(e, litellm.exceptions.RateLimitError):
        return LlmClientError(f"Rate limited by provider: reduce request frequency. {e}")
    elif isinstance(e, litellm.exceptions.APIConnectionError):
        return LlmClientError(f"Cannot reach LLM provider: check network connectivity. {e}")
    elif isinstance(e, litellm.exceptions.BadRequestError):
        return LlmClientError(f"Invalid request: {e}")
    else:
        return LlmClientError(f"LLM request failed: {e}")


class LlmClient:
    """Client for interacting with LLM providers via LiteLLM."""

    def __init__(self, config: LlmConfig) -> None:
        """Initialize the LLM client.

        Args:
            config: LLM configuration.
        """
        self.config = config
        self._configure_litellm()

    def _configure_litellm(self) -> None:
        """Configure LiteLLM with the provider settings.

        Note: LiteLLM requires API keys to be set as environment variables.
        This is by design - LiteLLM reads credentials from specific env vars
        per provider. The keys are set here for the process lifetime.
        """
        # Set API keys based on provider
        if self.config.provider == "anthropic" and self.config.api_key:
            litellm.api_key = self.config.api_key
            os.environ["ANTHROPIC_API_KEY"] = self.config.api_key
        elif self.config.provider == "openai" and self.config.api_key:
            litellm.api_key = self.config.api_key
            os.environ["OPENAI_API_KEY"] = self.config.api_key
        elif self.config.provider == "azure" and self.config.api_key:
            os.environ["AZURE_API_KEY"] = self.config.api_key
            if self.config.endpoint:
                os.environ["AZURE_API_BASE"] = self.config.endpoint

        # Set custom endpoint for Ollama
        if self.config.provider == "ollama" and self.config.endpoint:
            os.environ["OLLAMA_API_BASE"] = self.config.endpoint

    @classmethod
    def from_env(cls) -> "LlmClient":
        """Create an LlmClient from environment variables.

        Returns:
            Configured LlmClient instance.

        Raises:
            LlmClientError: If configuration is invalid.
        """
        config = LlmConfig.from_env()
        return cls(config)

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0.0 = deterministic).
            model: Optional model override (e.g. for screening tier).
            **kwargs: Additional arguments passed to LiteLLM.

        Returns:
            The assistant's response text.

        Raises:
            LlmClientError: If the request fails.
        """
        effective_model = model or self.config.get_litellm_model()
        try:
            response = await litellm.acompletion(
                model=effective_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            # Extract the response text
            content = response.choices[0].message.content
            if content is None:
                return ""
            return content
        except Exception as e:
            raise _handle_litellm_error(e) from e

    def complete_sync(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a synchronous completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0.0 = deterministic).
            model: Optional model override (e.g. for screening tier).
            **kwargs: Additional arguments passed to LiteLLM.

        Returns:
            The assistant's response text.

        Raises:
            LlmClientError: If the request fails.
        """
        effective_model = model or self.config.get_litellm_model()
        try:
            response = litellm.completion(
                model=effective_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            # Extract the response text
            content = response.choices[0].message.content
            if content is None:
                return ""
            return content
        except Exception as e:
            raise _handle_litellm_error(e) from e

    async def test_connection(self) -> bool:
        """Test the LLM connection with a minimal request.

        Returns:
            True if connection is successful.

        Raises:
            LlmClientError: If connection test fails.
        """
        try:
            await self.complete(
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=10,
            )
            return True
        except LlmClientError:
            raise

    @property
    def provider(self) -> str:
        """Get the configured provider name."""
        return self.config.provider

    @property
    def model(self) -> str:
        """Get the configured model name."""
        return self.config.model

    @property
    def screening_model(self) -> str:
        """Get the screening model, falling back to the default model.

        Falls back to ``get_litellm_model()`` so that provider prefixes
        (e.g. ``azure/``, ``ollama/``) are applied correctly.
        """
        return self.config.screening_model or self.config.get_litellm_model()
