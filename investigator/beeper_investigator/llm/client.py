"""LLM client wrapper using LiteLLM for provider flexibility.

This module provides a unified interface to multiple LLM providers through LiteLLM.
Configuration is loaded from environment variables:
- BEEPER_LLM_PROVIDER: Provider name (anthropic, openai, azure, ollama)
- BEEPER_LLM_MODEL: Model identifier
- BEEPER_LLM_API_KEY: API key (not needed for Ollama)
- BEEPER_LLM_ENDPOINT: Custom endpoint (optional, required for Azure)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

import litellm

from beeper_investigator.llm.cache import LlmResponseCache
from beeper_investigator.llm.cost import CostTracker
from beeper_investigator.llm.retry import (
    RetryConfig,
    retry_with_backoff_async,
    retry_with_backoff_sync,
)
from beeper_investigator.llm.scrubber import PiiScrubber

logger = logging.getLogger(__name__)

ModelTier = Literal["screening", "standard", "deep_rca"]


@dataclass
class LlmConfig:
    """Configuration for the LLM client."""

    provider: str
    model: str
    api_key: str | None = None
    endpoint: str | None = None
    screening_model: str | None = None
    deep_rca_model: str | None = None
    embedding_model: str | None = None
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 256
    cache_enabled: bool = True
    retry_enabled: bool = True
    retry_config: RetryConfig | None = None

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
        deep_rca_model = os.environ.get("BEEPER_LLM_DEEP_RCA_MODEL") or None
        embedding_model = os.environ.get("BEEPER_LLM_EMBEDDING_MODEL") or None
        cache_enabled = os.environ.get("BEEPER_LLM_CACHE_ENABLED", "true").lower() != "false"
        cache_ttl_seconds = int(os.environ.get("BEEPER_LLM_CACHE_TTL_SECONDS", "3600"))
        cache_max_entries = int(os.environ.get("BEEPER_LLM_CACHE_MAX_ENTRIES", "256"))
        retry_enabled = os.environ.get("BEEPER_LLM_RETRY_ENABLED", "true").lower() != "false"
        retry_config = RetryConfig.from_env() if retry_enabled else None

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
            deep_rca_model=deep_rca_model,
            embedding_model=embedding_model,
            cache_ttl_seconds=cache_ttl_seconds,
            cache_max_entries=cache_max_entries,
            cache_enabled=cache_enabled,
            retry_enabled=retry_enabled,
            retry_config=retry_config,
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


def is_retryable(e: Exception) -> bool:
    """Classify whether a LiteLLM exception is retryable.

    Retryable: APIConnectionError, RateLimitError, generic errors (timeouts).
    Non-retryable: AuthenticationError, BadRequestError.

    Args:
        e: The exception to classify.

    Returns:
        True if the error is transient and retrying may succeed.
    """
    if isinstance(e, litellm.exceptions.AuthenticationError):
        return False
    if isinstance(e, litellm.exceptions.BadRequestError):
        return False
    return True


class LlmClient:
    """Client for interacting with LLM providers via LiteLLM."""

    def __init__(self, config: LlmConfig) -> None:
        """Initialize the LLM client.

        Args:
            config: LLM configuration.
        """
        self.config = config
        self._model_usage: dict[str, int] = {}
        self._cache = LlmResponseCache(
            ttl_seconds=config.cache_ttl_seconds,
            max_entries=config.cache_max_entries,
        )
        self.cost_tracker = CostTracker()
        self.scrubber = PiiScrubber.from_env()
        self._retry_config = config.retry_config
        self._configure_litellm()

    def _configure_litellm(self) -> None:
        """Configure LiteLLM with the provider settings.

        Note: LiteLLM requires API keys to be set as environment variables.
        This is by design - LiteLLM reads credentials from specific env vars
        per provider. The keys are set here for the process lifetime.

        Security: All credentials (LLM API keys, Slack tokens, PagerDuty keys,
        Git tokens) are stored as K8s Secrets with encryption at rest and
        injected as environment variables via the Helm chart. Credentials are
        NEVER stored in Qdrant, config files, or application databases (NFR10).
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

        # Cache check (skip for non-deterministic temperature)
        if self.config.cache_enabled and temperature == 0.0:
            cached = self._cache.get(messages, effective_model, max_tokens, temperature)
            if cached is not None:
                logger.info("Cache hit for model %s", effective_model)
                self._model_usage[f"{effective_model}(cached)"] = (
                    self._model_usage.get(f"{effective_model}(cached)", 0) + 1
                )
                return cached

        # PII scrub messages before sending to LLM (deep copy — original unmodified)
        scrubbed_messages, audit_entries = self.scrubber.scrub_messages(messages)
        if audit_entries:
            self.scrubber.log_audit(audit_entries, method="complete")

        async def _do_acompletion() -> str:
            response = await litellm.acompletion(
                model=effective_model,
                messages=scrubbed_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            content: str | None = response.choices[0].message.content
            self._model_usage[effective_model] = (
                self._model_usage.get(effective_model, 0) + 1
            )
            usage = getattr(response, "usage", None)
            if usage:
                self.cost_tracker.record_call(
                    model=effective_model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            if self.config.cache_enabled and temperature == 0.0 and content:
                self._cache.put(messages, effective_model, max_tokens, temperature, content)
            if content is None:
                return ""
            return content

        try:
            if self._retry_config:
                result: str = await retry_with_backoff_async(
                    _do_acompletion, self._retry_config, is_retryable,
                )
                return result
            return await _do_acompletion()
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

        # Cache check (skip for non-deterministic temperature)
        if self.config.cache_enabled and temperature == 0.0:
            cached = self._cache.get(messages, effective_model, max_tokens, temperature)
            if cached is not None:
                logger.info("Cache hit for model %s", effective_model)
                self._model_usage[f"{effective_model}(cached)"] = (
                    self._model_usage.get(f"{effective_model}(cached)", 0) + 1
                )
                return cached

        # PII scrub messages before sending to LLM (deep copy — original unmodified)
        scrubbed_messages, audit_entries = self.scrubber.scrub_messages(messages)
        if audit_entries:
            self.scrubber.log_audit(audit_entries, method="complete_sync")

        def _do_completion() -> str:
            response = litellm.completion(
                model=effective_model,
                messages=scrubbed_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            content: str | None = response.choices[0].message.content
            self._model_usage[effective_model] = (
                self._model_usage.get(effective_model, 0) + 1
            )
            usage = getattr(response, "usage", None)
            if usage:
                self.cost_tracker.record_call(
                    model=effective_model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            if self.config.cache_enabled and temperature == 0.0 and content:
                self._cache.put(messages, effective_model, max_tokens, temperature, content)
            if content is None:
                return ""
            return content

        try:
            if self._retry_config:
                return retry_with_backoff_sync(
                    _do_completion, self._retry_config, is_retryable,
                )
            return _do_completion()
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

    def embed_sync(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            LlmClientError: If embedding model is not configured or the call fails.
        """
        if not self.config.embedding_model:
            raise LlmClientError(
                "Embedding model not configured (set BEEPER_LLM_EMBEDDING_MODEL)"
            )

        # PII scrub text before sending to embedding provider
        scrub_result = self.scrubber.scrub_text(text, field_location="embed_sync.input")
        scrubbed_text = scrub_result.scrubbed_text
        if scrub_result.audit_entries:
            self.scrubber.log_audit(scrub_result.audit_entries, method="embed_sync")

        def _do_embedding() -> list[float]:
            response = litellm.embedding(
                model=self.config.embedding_model,
                input=[scrubbed_text],
            )
            embedding: list[float] = response.data[0]["embedding"]
            return embedding

        try:
            if self._retry_config:
                return retry_with_backoff_sync(
                    _do_embedding, self._retry_config, is_retryable,
                )
            return _do_embedding()
        except LlmClientError:
            raise
        except Exception as e:
            raise _handle_litellm_error(e) from e

    @property
    def screening_model(self) -> str:
        """Get the screening model, falling back to the default model.

        Falls back to ``get_litellm_model()`` so that provider prefixes
        (e.g. ``azure/``, ``ollama/``) are applied correctly.
        """
        return self.config.screening_model or self.config.get_litellm_model()

    @property
    def deep_rca_model(self) -> str:
        """Get the deep RCA model, falling back to the default model.

        Falls back to ``get_litellm_model()`` so that provider prefixes
        (e.g. ``azure/``, ``ollama/``) are applied correctly.
        """
        return self.config.deep_rca_model or self.config.get_litellm_model()

    def select_model(self, tier: ModelTier) -> str:
        """Select model for the given task tier.

        Args:
            tier: Task tier determining model capability level.

        Returns:
            Model string formatted for LiteLLM.

        Raises:
            ValueError: If tier is not a recognized ModelTier value.
        """
        if tier == "screening":
            model = self.screening_model
        elif tier == "standard":
            model = self.config.get_litellm_model()
        elif tier == "deep_rca":
            model = self.deep_rca_model
        else:
            raise ValueError(f"Unknown model tier: {tier!r}")
        logger.info("Model tier '%s' selected: %s", tier, model)
        return model

    def get_model_usage(self) -> dict[str, int]:
        """Return a copy of the model usage counter dict."""
        return dict(self._model_usage)

    def reset_model_usage(self) -> None:
        """Clear model usage counters."""
        self._model_usage.clear()

    def clear_cache(self) -> None:
        """Clear all cached LLM responses."""
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache performance statistics."""
        return self._cache.get_cache_stats()

    def get_cost_stats(self) -> dict[str, Any]:
        """Return LLM cost statistics."""
        return self.cost_tracker.get_cost_stats()
