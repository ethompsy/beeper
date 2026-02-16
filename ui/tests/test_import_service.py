"""Tests for the import service."""

import pytest

from beeper_ui.services.import_service import (
    ImportResult,
    parse_markdown_file,
    parse_tags,
    validate_import_data,
)


class TestParseMarkdownFile:
    """Tests for parse_markdown_file function."""

    def test_parse_simple_markdown(self) -> None:
        """Test parsing simple markdown with H1 title."""
        content = """# Database Connection Runbook

## Overview

This runbook covers database connection issues.

## Steps

1. Check connection string
2. Verify credentials
"""
        result = parse_markdown_file(content, "runbook.md")

        assert result["title"] == "Database Connection Runbook"
        assert "## Overview" in result["content"]
        assert result["service"] is None
        assert result["tags"] == []

    def test_parse_with_yaml_front_matter(self) -> None:
        """Test parsing markdown with YAML front matter."""
        content = """---
title: API Gateway Runbook
service: api-gateway
tags:
  - networking
  - debug
---

# API Gateway Runbook

Content here.
"""
        result = parse_markdown_file(content, "api.md")

        assert result["title"] == "API Gateway Runbook"
        assert result["service"] == "api-gateway"
        assert result["tags"] == ["networking", "debug"]
        assert "Content here." in result["content"]

    def test_parse_uses_filename_as_fallback_title(self) -> None:
        """Test that filename is used when no title is found."""
        content = "Just some plain content without a heading."

        result = parse_markdown_file(content, "my-runbook.md")

        assert result["title"] == "my-runbook.md"
        assert result["content"] == "Just some plain content without a heading."

    def test_parse_extracts_title_from_h1(self) -> None:
        """Test that title is extracted from first H1."""
        content = """Some preamble text

# The Real Title

More content after.
"""
        result = parse_markdown_file(content, "file.md")

        assert result["title"] == "The Real Title"

    def test_parse_front_matter_overrides_h1(self) -> None:
        """Test that YAML front matter title takes precedence over H1."""
        content = """---
title: Front Matter Title
---

# H1 Title

Content.
"""
        result = parse_markdown_file(content, "file.md")

        assert result["title"] == "Front Matter Title"

    def test_parse_empty_front_matter(self) -> None:
        """Test parsing with empty front matter."""
        content = """---
---

# Title Here

Content.
"""
        result = parse_markdown_file(content, "file.md")

        assert result["title"] == "Title Here"

    def test_parse_front_matter_with_tags_as_string(self) -> None:
        """Test parsing front matter with tags as comma-separated string."""
        content = """---
title: Test
tags: one, two, three
---

Content.
"""
        result = parse_markdown_file(content, "file.md")

        # Tags as string should be split
        assert result["tags"] == ["one", "two", "three"]


class TestValidateImportData:
    """Tests for validate_import_data function."""

    def test_valid_data(self) -> None:
        """Test validation passes with valid data."""
        errors = validate_import_data(
            title="Valid Title",
            content="This is valid content that is long enough.",
            service="payments",
            tags=["tag1", "tag2"],
        )

        assert errors == []

    def test_title_too_short(self) -> None:
        """Test validation fails when title is too short."""
        errors = validate_import_data(
            title="AB",
            content="Valid content here.",
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "at least 3 characters" in errors[0]

    def test_title_too_long(self) -> None:
        """Test validation fails when title is too long."""
        errors = validate_import_data(
            title="A" * 201,
            content="Valid content here.",
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "under 200 characters" in errors[0]

    def test_content_too_short(self) -> None:
        """Test validation fails when content is too short."""
        errors = validate_import_data(
            title="Valid Title",
            content="Short",
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "at least 10 characters" in errors[0]

    def test_content_too_long(self) -> None:
        """Test validation fails when content is too long."""
        errors = validate_import_data(
            title="Valid Title",
            content="X" * 100001,
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "exceeds maximum size" in errors[0]

    def test_invalid_tag_format(self) -> None:
        """Test validation fails with invalid tag characters."""
        errors = validate_import_data(
            title="Valid Title",
            content="Valid content here.",
            service=None,
            tags=["valid-tag", "invalid tag", "another@bad"],
        )

        assert len(errors) == 2
        assert any("invalid tag" in e for e in errors)
        assert any("another@bad" in e for e in errors)

    def test_valid_tag_formats(self) -> None:
        """Test validation accepts valid tag formats."""
        errors = validate_import_data(
            title="Valid Title",
            content="Valid content here.",
            service=None,
            tags=["simple", "with-hyphen", "with_underscore", "CamelCase", "123numbers"],
        )

        assert errors == []

    def test_empty_title(self) -> None:
        """Test validation fails with empty title."""
        errors = validate_import_data(
            title="",
            content="Valid content here.",
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "at least 3 characters" in errors[0]

    def test_whitespace_only_title(self) -> None:
        """Test validation fails with whitespace-only title."""
        errors = validate_import_data(
            title="   ",
            content="Valid content here.",
            service=None,
            tags=[],
        )

        assert len(errors) == 1
        assert "at least 3 characters" in errors[0]

    def test_multiple_errors(self) -> None:
        """Test that multiple validation errors are returned."""
        errors = validate_import_data(
            title="",
            content="short",
            service=None,
            tags=["bad tag"],
        )

        assert len(errors) == 3


class TestParseTags:
    """Tests for parse_tags function."""

    def test_parse_comma_separated(self) -> None:
        """Test parsing comma-separated tags."""
        tags = parse_tags("one, two, three")
        assert tags == ["one", "two", "three"]

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string returns empty list."""
        tags = parse_tags("")
        assert tags == []

    def test_parse_strips_whitespace(self) -> None:
        """Test that whitespace is stripped from tags."""
        tags = parse_tags("  one  ,  two  ,  three  ")
        assert tags == ["one", "two", "three"]

    def test_parse_filters_empty_tags(self) -> None:
        """Test that empty tags are filtered out."""
        tags = parse_tags("one,,two,,,three")
        assert tags == ["one", "two", "three"]

    def test_parse_single_tag(self) -> None:
        """Test parsing single tag."""
        tags = parse_tags("single")
        assert tags == ["single"]


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating successful import result."""
        result = ImportResult(
            success=True,
            entry_id="kb-123",
            title="Test Entry",
        )

        assert result.success is True
        assert result.entry_id == "kb-123"
        assert result.title == "Test Entry"
        assert result.warnings == []
        assert result.error is None
        assert result.duplicate_of is None

    def test_failed_result(self) -> None:
        """Test creating failed import result."""
        result = ImportResult(
            success=False,
            title="Failed Entry",
            error="Content too short",
        )

        assert result.success is False
        assert result.entry_id is None
        assert result.error == "Content too short"

    def test_duplicate_result(self) -> None:
        """Test creating duplicate detection result."""
        result = ImportResult(
            success=False,
            title="Duplicate Entry",
            duplicate_of="kb-existing-456",
        )

        assert result.success is False
        assert result.duplicate_of == "kb-existing-456"

    def test_result_with_warnings(self) -> None:
        """Test creating result with warnings."""
        result = ImportResult(
            success=True,
            entry_id="kb-789",
            title="Entry with Warnings",
            warnings=["No service specified", "Tags were truncated"],
        )

        assert result.success is True
        assert len(result.warnings) == 2
