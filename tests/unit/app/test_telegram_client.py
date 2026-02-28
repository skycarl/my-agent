import pytest

from app.core.telegram_client import markdown_to_telegram_html


class TestMarkdownToTelegramHtml:
    """Tests for markdown_to_telegram_html conversion."""

    def test_bold(self):
        assert markdown_to_telegram_html("**bold**") == "<b>bold</b>"

    def test_bold_in_sentence(self):
        result = markdown_to_telegram_html("This is **important** stuff")
        assert result == "This is <b>important</b> stuff"

    def test_italic_asterisk(self):
        assert markdown_to_telegram_html("*italic*") == "<i>italic</i>"

    def test_inline_code(self):
        assert markdown_to_telegram_html("`some_code`") == "<code>some_code</code>"

    def test_code_block(self):
        result = markdown_to_telegram_html("```\nprint('hi')\n```")
        assert "<pre>" in result
        assert "print(&#x27;hi&#x27;)" in result

    def test_code_block_with_language(self):
        result = markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert "<pre>" in result

    def test_html_escaping(self):
        result = markdown_to_telegram_html("use <html> & stuff")
        assert "&lt;html&gt;" in result
        assert "&amp;" in result

    def test_bullet_list_dash(self):
        result = markdown_to_telegram_html("- item one\n- item two")
        assert result == "• item one\n• item two"

    def test_bullet_list_asterisk(self):
        result = markdown_to_telegram_html("* item one\n* item two")
        assert result == "• item one\n• item two"

    def test_plain_text_passthrough(self):
        text = "Just a normal message with no formatting."
        assert markdown_to_telegram_html(text) == text

    def test_mixed_formatting(self):
        text = "**bold** and *italic* and `code`"
        result = markdown_to_telegram_html(text)
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_realistic_agent_output(self):
        """Test with output similar to what the screenshot showed."""
        text = (
            "You have 1 active commute override:\n\n"
            "- **2026-02-28** — **commute_day** — \"Driving into downtown today\" "
            "(ID: **ce874964**)"
        )
        result = markdown_to_telegram_html(text)
        assert "<b>2026-02-28</b>" in result
        assert "<b>commute_day</b>" in result
        assert "<b>ce874964</b>" in result
        assert "**" not in result
        assert result.startswith("You have 1 active commute override:")

    def test_ampersand_in_text(self):
        assert "&amp;" in markdown_to_telegram_html("A & B")

    def test_no_double_escape(self):
        """Ensure we don't produce &amp;amp; etc."""
        result = markdown_to_telegram_html("A & B")
        assert "&amp;amp;" not in result
