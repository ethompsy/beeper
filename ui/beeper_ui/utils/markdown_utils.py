"""Markdown rendering utilities with XSS protection.

This module provides safe markdown rendering for the Knowledge Base wiki.
All markdown output is sanitized to prevent XSS attacks.
"""

import bleach
import markdown
from flask import Flask
from markupsafe import Markup

# Allowed HTML tags for sanitized output
ALLOWED_TAGS = [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "pre",
    "code",
    "blockquote",
    "a",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "br",
    "hr",
    "span",
    "div",
]

# Allowed attributes for HTML tags
# Note: img tag removed for security - KB content shouldn't need inline images
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "div": ["class"],
    "th": ["align"],
    "td": ["align"],
}

# Allowed URL protocols for links
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# Markdown extensions to enable
MARKDOWN_EXTENSIONS = [
    "tables",
    "fenced_code",
    "codehilite",
    "nl2br",
    "sane_lists",
]


def render_markdown(content: str) -> str:
    """Render markdown content to sanitized HTML.

    Args:
        content: The markdown content to render

    Returns:
        Sanitized HTML string safe for display.
    """
    if not content:
        return ""

    # Convert markdown to HTML
    html = markdown.markdown(
        content,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs={
            "codehilite": {
                "css_class": "highlight",
                "guess_lang": False,
            }
        },
    )

    # Sanitize the HTML output
    clean_html = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )

    return clean_html


def strip_markdown(content: str) -> str:
    """Strip markdown formatting to plain text.

    Useful for generating previews without markdown syntax.

    Args:
        content: The markdown content to strip

    Returns:
        Plain text with markdown formatting removed.
    """
    if not content:
        return ""

    # Convert markdown to HTML, then strip all tags
    html = markdown.markdown(content, extensions=MARKDOWN_EXTENSIONS)
    return bleach.clean(html, tags=[], strip=True)


def highlight_query_terms(text: str, query: str) -> str:
    """Highlight query terms in text with <mark> tags.

    Performs case-insensitive highlighting of query words.

    Args:
        text: The text to highlight in
        query: The search query (space-separated terms)

    Returns:
        Text with query terms wrapped in <mark> tags.
    """
    if not text or not query:
        return text

    import re

    # Split query into terms, filter empty strings
    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        return text

    # Build regex pattern for all terms (case-insensitive)
    # Escape special regex characters in each term
    escaped_terms = [re.escape(term) for term in terms]
    pattern = r'\b(' + '|'.join(escaped_terms) + r')\b'

    # Replace matches with highlighted version
    def replace_match(match: re.Match[str]) -> str:
        return f'<mark>{match.group(0)}</mark>'

    return re.sub(pattern, replace_match, text, flags=re.IGNORECASE)


def setup_markdown_filter(app: Flask) -> None:
    """Register the markdown Jinja2 filters with the Flask app.

    Args:
        app: Flask application instance
    """

    @app.template_filter("markdown")
    def markdown_filter(content: str) -> Markup:
        """Jinja2 filter to render markdown content safely.

        Args:
            content: The markdown content to render

        Returns:
            Markup object with sanitized HTML.
        """
        return Markup(render_markdown(content))

    @app.template_filter("strip_markdown")
    def strip_markdown_filter(content: str) -> str:
        """Jinja2 filter to strip markdown to plain text.

        Args:
            content: The markdown content to strip

        Returns:
            Plain text with markdown formatting removed.
        """
        return strip_markdown(content)

    @app.template_filter("highlight_query")
    def highlight_query_filter(content: str, query: str) -> Markup:
        """Jinja2 filter to highlight query terms in text.

        Args:
            content: The text to highlight in
            query: The search query

        Returns:
            Markup object with highlighted terms.
        """
        return Markup(highlight_query_terms(content, query))
