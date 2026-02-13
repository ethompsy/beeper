"""Tests for markdown rendering utilities."""

from flask import Flask

from beeper_ui.utils.markdown_utils import (
    highlight_query_terms,
    render_markdown,
    setup_markdown_filter,
    strip_markdown,
)


class TestRenderMarkdown:
    """Tests for render_markdown function."""

    def test_render_basic_text(self) -> None:
        """Test rendering basic markdown text."""
        result = render_markdown("Hello **world**")
        assert "<strong>world</strong>" in result
        assert "<p>" in result

    def test_render_empty_content(self) -> None:
        """Test rendering empty content."""
        assert render_markdown("") == ""
        assert render_markdown(None) == ""  # type: ignore

    def test_render_headings(self) -> None:
        """Test rendering markdown headings."""
        result = render_markdown("# Heading 1\n## Heading 2")
        assert "<h1>Heading 1</h1>" in result
        assert "<h2>Heading 2</h2>" in result

    def test_render_code_blocks(self) -> None:
        """Test rendering fenced code blocks."""
        result = render_markdown("```python\nprint('hello')\n```")
        assert "<pre" in result
        assert "<code" in result
        assert "print" in result

    def test_render_inline_code(self) -> None:
        """Test rendering inline code."""
        result = render_markdown("Use `var` for variables")
        assert "<code>var</code>" in result

    def test_render_lists(self) -> None:
        """Test rendering lists."""
        result = render_markdown("- Item 1\n- Item 2")
        assert "<ul>" in result
        assert "<li>Item 1</li>" in result

    def test_render_tables(self) -> None:
        """Test rendering markdown tables."""
        table = "| Col1 | Col2 |\n|------|------|\n| A | B |"
        result = render_markdown(table)
        assert "<table>" in result
        assert "<th>Col1</th>" in result

    def test_render_links(self) -> None:
        """Test rendering links preserves href."""
        result = render_markdown("[Click here](https://example.com)")
        assert '<a href="https://example.com">' in result
        assert "Click here</a>" in result

    def test_render_blockquote(self) -> None:
        """Test rendering blockquotes."""
        result = render_markdown("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result


class TestXSSPrevention:
    """Tests for XSS prevention in markdown rendering."""

    def test_strips_script_tags(self) -> None:
        """Test that script tags are stripped.

        Note: bleach strips the tags but may leave the text content.
        The key is that the <script> tags are removed so the browser
        won't execute it as JavaScript.
        """
        malicious = '<script>alert("xss")</script>'
        result = render_markdown(malicious)
        assert "<script>" not in result
        assert "</script>" not in result

    def test_strips_onclick_attributes(self) -> None:
        """Test that onclick attributes are stripped."""
        malicious = '<div onclick="alert(1)">Click me</div>'
        result = render_markdown(malicious)
        assert "onclick" not in result

    def test_strips_javascript_urls(self) -> None:
        """Test that javascript: URLs are handled."""
        malicious = '[Click](javascript:alert(1))'
        result = render_markdown(malicious)
        # Should strip the javascript URL
        assert "javascript:" not in result

    def test_strips_onerror_in_img(self) -> None:
        """Test that onerror in img tags is stripped."""
        malicious = '<img src="x" onerror="alert(1)">'
        result = render_markdown(malicious)
        assert "onerror" not in result

    def test_strips_style_attribute(self) -> None:
        """Test that style attributes are stripped."""
        malicious = '<div style="background:url(javascript:alert(1))">test</div>'
        result = render_markdown(malicious)
        assert "style=" not in result

    def test_strips_data_urls_in_script(self) -> None:
        """Test that data URLs with scripts are stripped."""
        malicious = '<a href="data:text/html,<script>alert(1)</script>">Click</a>'
        result = render_markdown(malicious)
        # Should preserve the link but remove dangerous content
        assert "data:text/html" not in result or "<script>" not in result

    def test_preserves_safe_html(self) -> None:
        """Test that safe HTML elements are preserved."""
        safe = "<strong>Bold</strong> and <em>italic</em>"
        result = render_markdown(safe)
        assert "<strong>Bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_strips_img_tags(self) -> None:
        """Test that img tags are stripped for security.

        Inline images are removed to prevent data: URL attacks.
        """
        malicious = '<img src="data:text/html,<script>alert(1)</script>">'
        result = render_markdown(malicious)
        assert "<img" not in result

    def test_strips_img_markdown(self) -> None:
        """Test that markdown images are stripped."""
        result = render_markdown("![alt text](https://example.com/img.png)")
        assert "<img" not in result


class TestMarkdownFilter:
    """Tests for Jinja2 markdown filter."""

    def test_filter_registration(self) -> None:
        """Test that markdown filter is registered."""
        app = Flask(__name__)
        setup_markdown_filter(app)
        assert "markdown" in app.jinja_env.filters

    def test_filter_renders_markdown(self) -> None:
        """Test that filter renders markdown correctly."""
        app = Flask(__name__)
        setup_markdown_filter(app)

        with app.app_context():
            template = app.jinja_env.from_string("{{ content|markdown }}")
            result = template.render(content="**bold**")
            assert "<strong>bold</strong>" in result

    def test_filter_returns_markup(self) -> None:
        """Test that filter returns Markup (safe string)."""
        app = Flask(__name__)
        setup_markdown_filter(app)

        with app.app_context():
            template = app.jinja_env.from_string("{{ content|markdown }}")
            result = template.render(content="test")
            # If it's Markup, it won't be escaped when rendered
            assert "&lt;" not in result or "<p>" in result

    def test_strip_markdown_filter_registered(self) -> None:
        """Test that strip_markdown filter is registered."""
        app = Flask(__name__)
        setup_markdown_filter(app)
        assert "strip_markdown" in app.jinja_env.filters

    def test_strip_markdown_filter_works(self) -> None:
        """Test that strip_markdown filter strips formatting."""
        app = Flask(__name__)
        setup_markdown_filter(app)

        with app.app_context():
            template = app.jinja_env.from_string("{{ content|strip_markdown }}")
            result = template.render(content="**bold** and _italic_")
            assert "bold" in result
            assert "italic" in result
            assert "<strong>" not in result
            assert "<em>" not in result


class TestStripMarkdown:
    """Tests for strip_markdown function."""

    def test_strips_bold_formatting(self) -> None:
        """Test stripping bold markdown."""
        result = strip_markdown("This is **bold** text")
        assert result == "This is bold text"
        assert "**" not in result

    def test_strips_italic_formatting(self) -> None:
        """Test stripping italic markdown."""
        result = strip_markdown("This is _italic_ text")
        assert "italic" in result
        assert "_" not in result or result.count("_") == 0

    def test_strips_headings(self) -> None:
        """Test stripping heading markdown."""
        result = strip_markdown("# Heading\n\nParagraph")
        assert "Heading" in result
        assert "#" not in result

    def test_strips_links(self) -> None:
        """Test stripping link markdown."""
        result = strip_markdown("Click [here](https://example.com)")
        assert "here" in result
        assert "[" not in result
        assert "https://example.com" not in result

    def test_strips_code_blocks(self) -> None:
        """Test stripping code block markdown."""
        result = strip_markdown("```python\nprint('hello')\n```")
        assert "print" in result
        assert "```" not in result

    def test_strips_lists(self) -> None:
        """Test stripping list markdown."""
        result = strip_markdown("- Item 1\n- Item 2")
        assert "Item 1" in result
        assert "Item 2" in result

    def test_handles_empty_content(self) -> None:
        """Test handling empty content."""
        assert strip_markdown("") == ""
        assert strip_markdown(None) == ""  # type: ignore

    def test_strips_html_tags(self) -> None:
        """Test stripping any HTML tags in content."""
        result = strip_markdown("<script>alert(1)</script>Safe text")
        assert "<script>" not in result
        assert "Safe text" in result


class TestHighlightQueryTerms:
    """Tests for highlight_query_terms function."""

    def test_highlights_single_term(self) -> None:
        """Test highlighting a single query term."""
        result = highlight_query_terms("This is a database error", "database")
        assert "<mark>database</mark>" in result
        assert "This is a" in result

    def test_highlights_multiple_terms(self) -> None:
        """Test highlighting multiple query terms."""
        result = highlight_query_terms("Database connection timeout error", "database timeout")
        assert "<mark>Database</mark>" in result
        assert "<mark>timeout</mark>" in result

    def test_case_insensitive(self) -> None:
        """Test that highlighting is case-insensitive."""
        result = highlight_query_terms("DATABASE error in Database", "database")
        assert "<mark>DATABASE</mark>" in result
        assert "<mark>Database</mark>" in result

    def test_empty_text(self) -> None:
        """Test with empty text."""
        assert highlight_query_terms("", "query") == ""

    def test_empty_query(self) -> None:
        """Test with empty query."""
        text = "Some text"
        assert highlight_query_terms(text, "") == text
        assert highlight_query_terms(text, "   ") == text

    def test_no_matches(self) -> None:
        """Test when query terms are not found."""
        text = "This is some text"
        result = highlight_query_terms(text, "notfound")
        assert result == text
        assert "<mark>" not in result

    def test_special_regex_chars(self) -> None:
        """Test that special regex characters are escaped."""
        text = "Error in foo.bar() function"
        result = highlight_query_terms(text, "foo.bar()")
        # Should still work and not crash
        assert "Error in" in result

    def test_word_boundaries(self) -> None:
        """Test that only whole words are highlighted."""
        result = highlight_query_terms("The database is undateable", "data")
        # "data" should NOT match "database" or "undateable" due to word boundaries
        assert "<mark>" not in result

    def test_preserves_non_matching_text(self) -> None:
        """Test that non-matching text is preserved."""
        result = highlight_query_terms("Error: Connection failed", "failed")
        assert "Error: Connection" in result
        assert "<mark>failed</mark>" in result


class TestHighlightQueryFilter:
    """Tests for Jinja2 highlight_query filter."""

    def test_filter_registration(self) -> None:
        """Test that highlight_query filter is registered."""
        app = Flask(__name__)
        setup_markdown_filter(app)
        assert "highlight_query" in app.jinja_env.filters

    def test_filter_highlights_terms(self) -> None:
        """Test that filter highlights query terms."""
        app = Flask(__name__)
        setup_markdown_filter(app)

        with app.app_context():
            template = app.jinja_env.from_string(
                "{{ content|highlight_query(query) }}"
            )
            result = template.render(content="Database error", query="database")
            assert "<mark>Database</mark>" in result

    def test_filter_returns_markup(self) -> None:
        """Test that filter returns Markup (safe string)."""
        app = Flask(__name__)
        setup_markdown_filter(app)

        with app.app_context():
            template = app.jinja_env.from_string(
                "{{ content|highlight_query(query) }}"
            )
            result = template.render(content="Test text", query="test")
            # The <mark> tag should not be escaped
            assert "&lt;mark&gt;" not in result
            assert "<mark>Test</mark>" in result
