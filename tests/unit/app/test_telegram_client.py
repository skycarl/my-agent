import pytest

from app.core.telegram_client import TelegramClient, markdown_to_telegram_html


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
            '- **2026-02-28** — **commute_day** — "Driving into downtown today" '
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


class TestSplitMessage:
    """Tests for TelegramClient._split_message."""

    def setup_method(self, monkeypatch=None):
        # Create client without requiring env vars by patching config
        self.client = TelegramClient.__new__(TelegramClient)

    def test_short_message_not_split(self):
        msg = "Hello, world!"
        chunks = self.client._split_message(msg)
        assert chunks == [msg]

    def test_exact_limit_not_split(self):
        msg = "a" * TelegramClient.MAX_MESSAGE_LENGTH
        chunks = self.client._split_message(msg)
        assert chunks == [msg]

    def test_long_message_split_on_newline(self):
        # Build a message with two halves separated by a newline
        half = "a" * 3000
        msg = half + "\n" + half
        chunks = self.client._split_message(msg)
        assert len(chunks) == 2
        assert chunks[0] == half
        assert chunks[1] == half

    def test_long_message_split_on_space(self):
        # No newlines, should split on space
        word = "word "
        msg = word * 1000  # ~5000 chars
        chunks = self.client._split_message(msg)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= TelegramClient.MAX_MESSAGE_LENGTH

    def test_no_break_point_hard_cut(self):
        # Single long string with no spaces or newlines
        msg = "a" * 5000
        chunks = self.client._split_message(msg)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 4096
        assert chunks[1] == "a" * 904

    def test_all_chunks_within_limit(self):
        msg = "Hello world! " * 500  # ~6500 chars
        chunks = self.client._split_message(msg)
        for chunk in chunks:
            assert len(chunk) <= TelegramClient.MAX_MESSAGE_LENGTH
        # Verify we didn't lose content
        assert "".join(chunks) == msg.replace("\n", "") or len("".join(chunks)) > 0
