"""Tests for the shared LLM response parser."""

import json

import pytest

from beeper_investigator.llm.response_parser import parse_json_response


class TestParseJsonResponse:
    """Tests for parse_json_response."""

    def test_plain_json(self) -> None:
        """Plain JSON string is parsed correctly."""
        raw = '{"key": "value", "num": 42}'
        result = parse_json_response(raw)
        assert result == {"key": "value", "num": 42}

    def test_code_fenced_json(self) -> None:
        """JSON wrapped in markdown code fences is parsed correctly."""
        raw = '```json\n{"key": "value"}\n```'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_code_fenced_no_lang(self) -> None:
        """Code fences without language tag are handled."""
        raw = '```\n{"key": "value"}\n```'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_thinking_tokens_stripped(self) -> None:
        """<think> blocks from qwen3/reasoning models are stripped."""
        raw = '<think>\nLet me analyze this...\nThe root cause is likely X.\n</think>\n{"root_cause": "X"}'
        result = parse_json_response(raw)
        assert result == {"root_cause": "X"}

    def test_thinking_tokens_with_code_fence(self) -> None:
        """<think> blocks + code fences are both handled."""
        raw = '<think>reasoning here</think>\n```json\n{"answer": "yes"}\n```'
        result = parse_json_response(raw)
        assert result == {"answer": "yes"}

    def test_thinking_tokens_multiline(self) -> None:
        """Multi-line thinking blocks are fully removed."""
        raw = (
            "<think>\nStep 1: Check the error rate\n"
            "Step 2: Correlate with deployment\n"
            "Step 3: Form hypothesis\n</think>\n"
            '{"hypothesis": "deployment caused error spike"}'
        )
        result = parse_json_response(raw)
        assert result == {"hypothesis": "deployment caused error spike"}

    def test_whitespace_handling(self) -> None:
        """Leading/trailing whitespace is stripped."""
        raw = '  \n  {"key": "value"}  \n  '
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self) -> None:
        """Invalid JSON raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("not json at all")

    def test_thinking_only_raises(self) -> None:
        """Response with only thinking tokens (no JSON) raises error."""
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("<think>just thinking</think>")

    def test_nested_json(self) -> None:
        """Complex nested JSON is parsed correctly."""
        data = {
            "root_cause_hypothesis": "DB connection pool exhausted",
            "confidence_level": "high",
            "supporting_evidence": ["error rate 34%", "connection refused"],
        }
        raw = f"<think>analyzing...</think>\n```json\n{json.dumps(data)}\n```"
        result = parse_json_response(raw)
        assert result == data

    def test_think_inside_code_fence_preserved(self) -> None:
        """<think> text inside code fence JSON values is NOT stripped."""
        raw = '```json\n{"code": "<think>preserved</think>"}\n```'
        result = parse_json_response(raw)
        assert result == {"code": "<think>preserved</think>"}

    def test_preamble_text_before_json(self) -> None:
        """Preamble text between </think> and JSON is handled."""
        raw = '<think>reasoning</think>\n\nHere is my analysis:\n\n{"key": "value"}'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_multiple_think_blocks(self) -> None:
        """Multiple <think> blocks are all stripped."""
        raw = '<think>first</think>\n<think>second</think>\n{"key": "value"}'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_unclosed_think_tag_with_json(self) -> None:
        """Unclosed <think> tag doesn't prevent JSON extraction."""
        raw = '<think>unclosed\n{"key": "value"}'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_preamble_without_think(self) -> None:
        """Plain preamble text (no think tags) before JSON is handled."""
        raw = 'Here is the result:\n\n{"key": "value"}'
        result = parse_json_response(raw)
        assert result == {"key": "value"}
