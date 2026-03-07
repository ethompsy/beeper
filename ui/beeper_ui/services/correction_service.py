"""Correction service for processing natural language corrections via LLM.

This service uses litellm to process conversational corrections
to KB entries, returning structured acknowledgments of understood changes.
"""

import json
import logging
import os
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = (
    "You are Beeper, an AI SRE assistant. "
    "A user is providing a correction to a Knowledge Base entry.\n\n"
    "**KB Entry Title:** {title}\n"
    "**KB Entry Content:**\n{content}\n\n"
    "The user will describe what should be changed in natural language. "
    "Your job is to:\n"
    "1. Understand what changes the user wants\n"
    "2. Summarize the understood changes clearly\n"
    "3. Respond with a JSON object (and ONLY JSON, no markdown fencing):\n\n"
    '{{"summary": "Brief description of what will change", '
    '"understood_changes": ["Change 1", "Change 2"]}}\n\n'
    "Be concise and precise. If the correction is unclear, "
    "explain what you understood and ask for clarification "
    "in the summary field."
)

REPLY_SYSTEM_PROMPT_TEMPLATE = (
    "You are Beeper, an AI SRE assistant. "
    "A user is continuing a correction conversation about a "
    "Knowledge Base entry.\n\n"
    "**KB Entry Title:** {title}\n"
    "**KB Entry Content:**\n{content}\n\n"
    "The user is providing additional clarification or follow-up "
    "to a previous correction. Review the conversation history "
    "and the new message, then respond with an updated understanding.\n\n"
    "Respond with a JSON object (and ONLY JSON, no markdown fencing):\n\n"
    '{{"summary": "Updated description of what will change", '
    '"understood_changes": ["Change 1", "Change 2"]}}'
)


class CorrectionServiceError(Exception):
    """Exception raised by correction service operations."""

    pass


class CorrectionService:
    """Service for processing corrections using LLM via litellm."""

    def __init__(self) -> None:
        """Initialize the correction service from environment variables.

        Environment variables:
            BEEPER_LLM_PROVIDER: Provider name (anthropic, openai, azure, ollama)
            BEEPER_LLM_MODEL: Model identifier
            BEEPER_LLM_API_KEY: API key
        """
        provider = os.environ.get("BEEPER_LLM_PROVIDER", "").lower()
        model = os.environ.get("BEEPER_LLM_MODEL", "")
        api_key = os.environ.get("BEEPER_LLM_API_KEY")

        if not provider or not model:
            raise CorrectionServiceError(
                "BEEPER_LLM_PROVIDER and BEEPER_LLM_MODEL environment variables are required"
            )

        # Format model string for litellm
        if provider == "azure" and not model.startswith("azure/"):
            self._model = f"azure/{model}"
        elif provider == "ollama" and not model.startswith("ollama/"):
            self._model = f"ollama/{model}"
        else:
            self._model = model

        # Set API keys for litellm
        if provider == "anthropic" and api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "openai" and api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "azure" and api_key:
            os.environ["AZURE_API_KEY"] = api_key

    def _complete_sync(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Send a synchronous completion request via litellm.

        Returns:
            The assistant's response text.

        Raises:
            CorrectionServiceError: If the request fails.
        """
        try:
            response = litellm.completion(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return content if content else ""
        except Exception as e:
            raise CorrectionServiceError(f"LLM request failed: {e}") from e

    def process_correction(
        self,
        entry_content: str,
        entry_title: str,
        correction_text: str,
    ) -> dict[str, Any]:
        """Process a correction and return structured acknowledgment.

        Args:
            entry_content: The KB entry content being corrected
            entry_title: The KB entry title
            correction_text: The user's natural language correction

        Returns:
            Dict with 'summary' and 'understood_changes' keys.

        Raises:
            CorrectionServiceError: If LLM processing fails.
        """
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            title=entry_title,
            content=entry_content,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": correction_text},
        ]

        try:
            response = self._complete_sync(messages=messages)
            return self._parse_response(response)
        except CorrectionServiceError:
            raise
        except Exception as e:
            raise CorrectionServiceError(f"Failed to process correction: {e}") from e

    def process_reply(
        self,
        entry_content: str,
        entry_title: str,
        conversation_history: list[dict[str, str]],
        reply_text: str,
    ) -> dict[str, Any]:
        """Process a follow-up reply in a correction conversation.

        Args:
            entry_content: The KB entry content being corrected
            entry_title: The KB entry title
            conversation_history: Previous messages in the conversation
            reply_text: The user's new reply

        Returns:
            Dict with 'summary' and 'understood_changes' keys.

        Raises:
            CorrectionServiceError: If LLM processing fails.
        """
        system_prompt = REPLY_SYSTEM_PROMPT_TEMPLATE.format(
            title=entry_title,
            content=entry_content,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        messages.append({"role": "user", "content": reply_text})

        try:
            response = self._complete_sync(messages=messages)
            return self._parse_response(response)
        except CorrectionServiceError:
            raise
        except Exception as e:
            raise CorrectionServiceError(f"Failed to process reply: {e}") from e

    @staticmethod
    def _parse_response(response: str) -> dict[str, Any]:
        """Parse LLM response into structured correction acknowledgment.

        Falls back to plain text if JSON parsing fails.
        """
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            data = json.loads(cleaned)
            return {
                "summary": data.get("summary", response),
                "understood_changes": data.get("understood_changes", []),
            }
        except (json.JSONDecodeError, KeyError):
            return {
                "summary": response,
                "understood_changes": [response],
            }


# Module-level singleton
_correction_service: Optional[CorrectionService] = None


def get_correction_service() -> CorrectionService:
    """Get the global correction service instance.

    Returns:
        CorrectionService singleton instance.

    Raises:
        CorrectionServiceError: If LLM client cannot be initialized.
    """
    global _correction_service
    if _correction_service is None:
        _correction_service = CorrectionService()
    return _correction_service


def reset_correction_service() -> None:
    """Reset the global correction service singleton (for testing)."""
    global _correction_service
    _correction_service = None
