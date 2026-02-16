"""Import service for runbook import functionality.

This module provides parsing, validation, and processing for
importing runbooks into the Knowledge Base.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Validation constants
MIN_TITLE_LENGTH = 3
MAX_TITLE_LENGTH = 200
MIN_CONTENT_LENGTH = 10
MAX_CONTENT_LENGTH = 100000

# Valid tag pattern (alphanumeric, hyphen, underscore)
TAG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class ImportResult:
    """Result of a runbook import operation."""

    success: bool
    entry_id: Optional[str] = None
    title: str = ""
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    duplicate_of: Optional[str] = None


def parse_tags(tags_string: str) -> list[str]:
    """Parse comma-separated tags string into a list.

    Args:
        tags_string: Comma-separated tags (e.g., "tag1, tag2, tag3")

    Returns:
        List of stripped, non-empty tag strings.
    """
    if not tags_string:
        return []

    tags = [tag.strip() for tag in tags_string.split(",")]
    return [tag for tag in tags if tag]


def parse_markdown_file(content: str, filename: str) -> dict[str, Any]:
    """Parse markdown file, extracting front matter if present.

    Supports YAML front matter for metadata extraction:
    ```
    ---
    title: Runbook Title
    service: service-name
    tags:
      - tag1
      - tag2
    ---

    # Content starts here
    ```

    If no front matter, extracts title from first H1 heading.
    Falls back to filename if no title found.

    Args:
        content: Raw markdown content
        filename: Original filename (used as fallback title)

    Returns:
        Dict with keys: title, service, tags, content
    """
    lines = content.split("\n")
    front_matter: dict[str, Any] = {}
    content_body = content

    # Check for YAML front matter
    if lines and lines[0].strip() == "---":
        try:
            # Find the closing ---
            end_idx = None
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    end_idx = i
                    break

            if end_idx is not None:
                # Parse YAML front matter
                yaml_content = "\n".join(lines[1:end_idx])
                if yaml_content.strip():
                    front_matter = yaml.safe_load(yaml_content) or {}

                # Content is everything after front matter
                content_body = "\n".join(lines[end_idx + 1 :]).strip()
            else:
                # No closing ---, treat entire content as body (no front matter)
                logger.warning("YAML front matter has no closing '---', ignoring")
        except (yaml.YAMLError, ValueError, IndexError) as e:
            logger.warning(f"Failed to parse YAML front matter: {e}")

    # Handle tags that might be a string instead of a list
    if "tags" in front_matter and isinstance(front_matter["tags"], str):
        front_matter["tags"] = parse_tags(front_matter["tags"])

    # Extract title from first H1 if not in front matter
    if "title" not in front_matter:
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("# "):
                front_matter["title"] = line_stripped[2:].strip()
                break

    return {
        "title": front_matter.get("title", filename),
        "service": front_matter.get("service"),
        "tags": front_matter.get("tags", []),
        "content": content_body,
    }


def validate_import_data(
    title: str,
    content: str,
    service: Optional[str],
    tags: list[str],
) -> list[str]:
    """Validate import data and return list of errors.

    Args:
        title: Entry title
        content: Entry content
        service: Optional service name
        tags: List of tags

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Validate title
    title_stripped = title.strip() if title else ""
    if len(title_stripped) < MIN_TITLE_LENGTH:
        errors.append(f"Title must be at least {MIN_TITLE_LENGTH} characters")
    if len(title) > MAX_TITLE_LENGTH:
        errors.append(f"Title must be under {MAX_TITLE_LENGTH} characters")

    # Validate content
    content_stripped = content.strip() if content else ""
    if len(content_stripped) < MIN_CONTENT_LENGTH:
        errors.append(f"Content must be at least {MIN_CONTENT_LENGTH} characters")
    if len(content) > MAX_CONTENT_LENGTH:
        errors.append(f"Content exceeds maximum size ({MAX_CONTENT_LENGTH // 1000}KB)")

    # Validate tags
    for tag in tags:
        if not TAG_PATTERN.match(tag):
            errors.append(f"Invalid tag format: {tag}")

    return errors
