"""Shared LLM response parser for JSON extraction.

Handles common LLM output quirks:
- Markdown code fences (```json ... ```)
- Thinking tokens (<think>...</think>) from models like qwen3
- Preamble/postamble prose around JSON objects
- Reasoning blocks that themselves CONTAIN draft JSON / code fences
- Trailing prose and braces inside string values

The parser tries several extraction strategies in priority order and returns
the first that yields a valid JSON object. The ordering matters:

1. **After the last `</think>`** — a reasoning model's real answer always
   follows its final `</think>`. Taking this first means a ```json draft the
   model wrote *inside* its <think> block can't be mistaken for the answer
   (the bug that made qwen3 fall back to defaults on ~every investigation).
2. **Code fence on the raw text** — preserves a literal `<think>` that appears
   *inside* a fenced JSON value (which strategy 1 deliberately doesn't reach,
   because the only `</think>` there is part of the data).
3. **Think-stripped brace extraction** — handles unclosed/multiple think blocks
   and plain preamble prose with no fences.
"""

import json
import re
from typing import Any

# Complete <think>...</think> blocks (qwen3 and similar reasoning models).
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# JSON content within optional markdown code fences.
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _balanced_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` object in *text*, or None.

    String-aware: braces inside JSON string values (e.g. a PromQL query like
    ``rate{job="x"}``) do not prematurely close the object.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # unbalanced (e.g. response truncated mid-object)


def _extract_object(text: str) -> str | None:
    """Pull a JSON object out of *text*: prefer a code fence, else first balanced ``{}``."""
    fence = _CODE_FENCE_RE.search(text)
    if fence:
        inner = fence.group(1).strip()
        if inner.startswith("{"):
            return inner
        obj = _balanced_object(inner)
        if obj is not None:
            return obj
    return _balanced_object(text)


def parse_json_response(raw: str) -> dict[str, Any]:
    """Parse an LLM response string into a JSON dict.

    Tries several extraction strategies (see module docstring) and returns the
    first that parses as valid JSON.

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed JSON dict.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    candidates: list[str] = []

    # 1. The real answer follows the LAST </think> (reasoning models). Anything
    #    the model drafted inside its <think> block is discarded.
    if "</think>" in raw:
        after_think = raw.rsplit("</think>", 1)[1]
        obj = _extract_object(after_think)
        if obj is not None:
            candidates.append(obj)

    # 2. Code fence on the raw text — preserves a literal <think> that is part
    #    of a fenced JSON value (strategy 1 can't reach that case).
    fence = _CODE_FENCE_RE.search(raw)
    if fence:
        candidates.append(fence.group(1).strip())

    # 3. Strip complete <think> blocks, then extract an object (handles
    #    multiple blocks, plain preamble prose, braces in string values).
    stripped = _THINK_BLOCK_RE.sub("", raw)
    obj = _extract_object(stripped)
    if obj is not None:
        candidates.append(obj)

    for candidate in candidates:
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result

    # Nothing parsed — raise a clear error the callers catch (and fall back to
    # their step-specific defaults).
    return json.loads(stripped.strip())
