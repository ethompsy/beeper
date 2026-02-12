"""LLM client module for Beeper investigator.

This module provides a wrapper around LiteLLM for flexible LLM provider support.
Supported providers: anthropic, openai, azure, ollama
"""

from .client import LlmClient, LlmClientError, LlmConfig

__all__ = ["LlmClient", "LlmClientError", "LlmConfig"]
