"""Learning service for analyzing correction diffs and generating prompt adjustments.

This service uses litellm to analyze diffs between original and corrected KB entries,
categorize correction patterns, and generate prompt adjustments for future investigations.
"""

import json
import logging
import os
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT_TEMPLATE = (
    "You are analyzing a Knowledge Base correction to identify learning patterns. "
    "An SRE corrected Beeper's documentation. Compare the original and corrected content "
    "to identify what Beeper got wrong or missed.\n\n"
    "Categorize each change into one of these categories:\n"
    "- missing_context: Information Beeper should have included but didn't\n"
    "- incorrect_correlation: Beeper correlated the wrong signals or causes\n"
    "- wrong_conclusion: Beeper drew an incorrect conclusion from the evidence\n"
    "- unnecessary_info: Information Beeper included that was irrelevant or misleading\n"
    "- other: Changes that don't fit the above categories\n\n"
    "Respond with ONLY a JSON array (no markdown fencing):\n"
    '[{{"category": "missing_context", "description": "what was learned", '
    '"original_snippet": "relevant original text", '
    '"corrected_snippet": "relevant corrected text"}}]'
)

ADJUSTMENT_SYSTEM_PROMPT_TEMPLATE = (
    "You are synthesizing correction patterns into actionable prompt hints "
    "for an AI SRE investigator called Beeper. Based on accumulated learning "
    "patterns, generate concise, specific instructions that would prevent "
    "similar mistakes in future investigations.\n\n"
    "Each adjustment should be a direct, actionable instruction. "
    "Scope adjustments to the specific service when patterns are service-specific.\n\n"
    "Respond with ONLY a JSON object (no markdown fencing):\n"
    '{{"adjustments": ["instruction 1", "instruction 2"]}}'
)


class LearningServiceError(Exception):
    """Exception raised by learning service operations."""

    pass


class LearningService:
    """Service for analyzing correction diffs and generating prompt adjustments."""

    def __init__(self) -> None:
        """Initialize the learning service from environment variables."""
        provider = os.environ.get("BEEPER_LLM_PROVIDER", "").lower()
        model = os.environ.get("BEEPER_LLM_MODEL", "")
        api_key = os.environ.get("BEEPER_LLM_API_KEY")

        if not provider or not model:
            raise LearningServiceError(
                "BEEPER_LLM_PROVIDER and BEEPER_LLM_MODEL environment variables are required"
            )

        if provider == "azure" and not model.startswith("azure/"):
            self._model = f"azure/{model}"
        elif provider == "ollama" and not model.startswith("ollama/"):
            self._model = f"ollama/{model}"
        else:
            self._model = model

        if provider == "anthropic" and api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "openai" and api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "azure" and api_key:
            os.environ["AZURE_API_KEY"] = api_key

    def _complete_sync(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """Send a synchronous completion request via litellm."""
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
            raise LearningServiceError(f"LLM request failed: {e}") from e

    def analyze_correction(
        self,
        entry_content: str,
        revised_content: str,
        entry_title: str,
        service_name: str,
        correction_messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Analyze a correction diff and return categorized patterns.

        Args:
            entry_content: Original KB entry content
            revised_content: Corrected/revised content
            entry_title: KB entry title
            service_name: Service scope for the correction
            correction_messages: Correction conversation messages

        Returns:
            List of pattern dicts with category, description, original_snippet,
            corrected_snippet keys.

        Raises:
            LearningServiceError: If LLM processing fails.
        """
        conversation_summary = "\n".join(
            f"- {m['role']}: {m['content']}" for m in correction_messages
        )

        user_message = (
            f"**KB Entry Title:** {entry_title}\n"
            f"**Service:** {service_name}\n\n"
            f"**Original Content:**\n{entry_content}\n\n"
            f"**Corrected Content:**\n{revised_content}\n\n"
            f"**Correction Conversation:**\n{conversation_summary}"
        )

        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT_TEMPLATE},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self._complete_sync(messages=messages)
            return self._parse_patterns(response)
        except LearningServiceError:
            raise
        except Exception as e:
            raise LearningServiceError(f"Failed to analyze correction: {e}") from e

    def generate_prompt_adjustments(
        self,
        patterns: list[dict[str, Any]],
        service_name: Optional[str] = None,
    ) -> list[str]:
        """Generate prompt adjustments from accumulated learning patterns.

        Args:
            patterns: List of learning pattern dicts
            service_name: Service scope (None = general adjustments)

        Returns:
            List of actionable prompt adjustment strings.

        Raises:
            LearningServiceError: If LLM processing fails.
        """
        if not patterns:
            return []

        pattern_summary = "\n".join(
            f"- [{p.get('category', 'other')}] {p.get('description', '')}"
            for p in patterns
        )

        scope = f"service '{service_name}'" if service_name else "all services"
        user_message = (
            f"**Scope:** {scope}\n\n"
            f"**Accumulated Learning Patterns:**\n{pattern_summary}\n\n"
            f"Generate concise, actionable prompt adjustments to prevent "
            f"these mistakes in future investigations."
        )

        messages = [
            {"role": "system", "content": ADJUSTMENT_SYSTEM_PROMPT_TEMPLATE},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self._complete_sync(messages=messages, max_tokens=1024)
            return self._parse_adjustments(response)
        except LearningServiceError:
            raise
        except Exception as e:
            raise LearningServiceError(
                f"Failed to generate prompt adjustments: {e}"
            ) from e

    @staticmethod
    def _parse_patterns(response: str) -> list[dict[str, Any]]:
        """Parse LLM response into list of pattern dicts."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            data = json.loads(cleaned)
            if isinstance(data, list):
                return [
                    {
                        "category": p.get("category", "other"),
                        "description": p.get("description", ""),
                        "original_snippet": p.get("original_snippet", ""),
                        "corrected_snippet": p.get("corrected_snippet", ""),
                    }
                    for p in data
                ]
            return []
        except (json.JSONDecodeError, KeyError):
            return [
                {
                    "category": "other",
                    "description": response[:200],
                    "original_snippet": "",
                    "corrected_snippet": "",
                }
            ]

    def get_prompt_context(
        self,
        patterns: list[dict[str, Any]],
        service_name: Optional[str] = None,
    ) -> str:
        """Generate a concise prompt supplement from learning patterns.

        This creates a block of text that can be injected into investigation
        prompts to help Beeper avoid previously identified mistakes.

        Args:
            patterns: List of learning pattern dicts
            service_name: Service scope (None = general context)

        Returns:
            Prompt context string, or empty string if no patterns.
        """
        if not patterns:
            return ""

        adjustments = self.generate_prompt_adjustments(patterns, service_name)
        if not adjustments:
            return ""

        scope = f" for {service_name}" if service_name else ""
        lines = [f"Based on past corrections{scope}, keep these in mind:"]
        for adj in adjustments:
            lines.append(f"- {adj}")
        return "\n".join(lines)

    @staticmethod
    def _parse_adjustments(response: str) -> list[str]:
        """Parse LLM response into list of adjustment strings."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            data = json.loads(cleaned)
            adjustments = data.get("adjustments", [])
            return [str(a) for a in adjustments if a]
        except (json.JSONDecodeError, KeyError):
            return [response[:200]] if response.strip() else []


# Module-level singleton
_learning_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    """Get the global learning service instance."""
    global _learning_service
    if _learning_service is None:
        _learning_service = LearningService()
    return _learning_service


def reset_learning_service() -> None:
    """Reset the global learning service singleton (for testing)."""
    global _learning_service
    _learning_service = None
