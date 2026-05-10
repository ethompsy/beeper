"""Shared LLM response parser for JSON extraction.

Handles common LLM output quirks:
- Markdown code fences (```json ... ```)
- Thinking tokens (<think>...</think>) from models like qwen3
- Preamble/postamble text around JSON objects
- Leading/trailing whitespace
"""

import json
import re
from typing import Any

# Strip <think>...</think> blocks (qwen3 and similar reasoning models)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Match JSON content within optional markdown code fences
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def parse_json_response(raw: str) -> dict[str, Any]:
    """Parse an LLM response string into a JSON dict.

    Extraction order (to avoid corrupting JSON content):
    1. Extract from code fences first (protects content inside fences)
    2. If no code fence, strip thinking tokens from raw text
    3. Extract first JSON object from remaining text

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed JSON dict.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    # 1. Try code fences first — content inside is trusted (no think stripping)
    match = _CODE_FENCE_RE.search(raw)
    if match:
        return json.loads(match.group(1).strip())

    # 2. No code fence — strip thinking tokens from raw text
    text = _THINK_RE.sub("", raw)

    # 3. Try direct parse
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)

    # 4. Extract first JSON object (handles preamble text from LLMs)
    brace_idx = text.find("{")
    if brace_idx >= 0:
        candidate = text[brace_idx:].strip()
        return json.loads(candidate)

    # 5. Nothing worked
    return json.loads(stripped)
