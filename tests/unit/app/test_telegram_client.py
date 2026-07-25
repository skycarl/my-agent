from unittest.mock import AsyncMock, Mock, patch

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

    def test_heading(self):
        assert markdown_to_telegram_html("## Logistics") == "<b>Logistics</b>"

    def test_heading_levels(self):
        assert markdown_to_telegram_html("# Title") == "<b>Title</b>"
        assert markdown_to_telegram_html("### Sub") == "<b>Sub</b>"

    def test_heading_with_emoji_in_block(self):
        text = "## ⚠️ Need to know\n- item one"
        result = markdown_to_telegram_html(text)
        assert result == "<b>⚠️ Need to know</b>\n• item one"
        assert "##" not in result

    def test_hash_not_a_heading_without_space(self):
        """A bare # without a following space (e.g. a hashtag) is left alone."""
        assert markdown_to_telegram_html("#hashtag") == "#hashtag"

    def test_markdown_link(self):
        result = markdown_to_telegram_html("[fly.faa.gov](https://www.fly.faa.gov)")
        assert result == '<a href="https://www.fly.faa.gov">fly.faa.gov</a>'

    def test_markdown_link_escapes_ampersand_in_url(self):
        """URL query params with & must be escaped for Telegram's HTML href."""
        result = markdown_to_telegram_html(
            "[fly.faa.gov](https://www.fly.faa.gov/fly?ARPT=SEA&p=1)"
        )
        assert (
            result == '<a href="https://www.fly.faa.gov/fly?ARPT=SEA&amp;p=1">'
            "fly.faa.gov</a>"
        )
        assert "[" not in result and "(" not in result

    def test_markdown_link_in_sentence(self):
        result = markdown_to_telegram_html(
            "Check ([soundtransit.org](https://www.soundtransit.org/alerts)) for more."
        )
        assert (
            '<a href="https://www.soundtransit.org/alerts">soundtransit.org</a>'
            in result
        )
        assert "](" not in result

    def test_ampersand_in_text(self):
        assert "&amp;" in markdown_to_telegram_html("A & B")

    def test_no_double_escape(self):
        """Ensure we don't produce &amp;amp; etc."""
        result = markdown_to_telegram_html("A & B")
        assert "&amp;amp;" not in result


class TestCodeBlockProtection:
    """Formatting regexes must not inject tags inside <pre>/<code> —
    Telegram forbids nested entities there and rejects the message."""

    def test_comment_in_code_block_not_bolded(self):
        result = markdown_to_telegram_html("```python\n# comment\nx = 1\n```")
        assert "<pre># comment\nx = 1\n</pre>" in result
        assert "<b>" not in result

    def test_bold_markers_in_code_block_untouched(self):
        result = markdown_to_telegram_html("```\n**stars**\n```")
        assert "**stars**" in result
        assert "<b>" not in result

    def test_asterisks_in_code_block_not_italicized(self):
        result = markdown_to_telegram_html("```\na * b * c\n```")
        assert "a * b * c" in result
        assert "<i>" not in result

    def test_link_syntax_in_code_block_untouched(self):
        result = markdown_to_telegram_html("```\n[x](http://y)\n```")
        assert "[x](http://y)" in result
        assert "<a " not in result

    def test_inline_code_protected(self):
        result = markdown_to_telegram_html("`a * b` and `**x**`")
        assert "<code>a * b</code>" in result
        assert "<code>**x**</code>" in result
        assert "<b>" not in result
        assert "<i>" not in result

    def test_code_block_contents_still_escaped(self):
        result = markdown_to_telegram_html("```\nif a < b & c:\n```")
        assert "&lt;" in result
        assert "&amp;" in result

    def test_formatting_outside_code_block_still_applied(self):
        result = markdown_to_telegram_html("**bold**\n```\n# code\n```\n*it*")
        assert "<b>bold</b>" in result
        assert "<pre># code\n</pre>" in result
        assert "<i>it</i>" in result


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
        # Verify no content was lost (whitespace at split boundaries is dropped)
        assert "".join(chunks).replace(" ", "") == msg.replace(" ", "")

    def test_leading_space_no_infinite_loop(self):
        # Regression test: a long unbroken string whose only break point is
        # at index 0 used to loop forever producing empty chunks
        msg = " " + "x" * 5000
        chunks = self.client._split_message(msg)
        assert all(chunks)  # no empty chunks
        assert "".join(chunks).replace(" ", "") == msg.replace(" ", "")
        for chunk in chunks:
            assert len(chunk) <= TelegramClient.MAX_MESSAGE_LENGTH

    def test_custom_max_length_respected(self):
        msg = "word " * 200
        chunks = self.client._split_message(msg, 100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100


class TestMarkdownChunksFitAfterConversion:
    """Regression: markdown split then converted must still fit Telegram's limit.

    Converting to HTML only grows the text (escaping &/</>, <b> tags, link
    expansion), so splitting the raw markdown at the full 4096 limit produced
    chunks that Telegram rejected with a 400 — and send_message bails on the
    first failure, so the user received nothing at all.
    """

    def setup_method(self):
        self.client = TelegramClient.__new__(TelegramClient)

    @pytest.mark.parametrize(
        "unit",
        [
            "**bold heading here** and text with & ampersands and <angles> ",
            "[a link](https://example.com/some/path) & more text ",
            "plain text with lots of & and < and > characters everywhere ",
        ],
    )
    def test_converted_chunks_within_limit(self, unit):
        raw = unit * 200
        assert len(raw) > TelegramClient.MAX_MESSAGE_LENGTH

        raw_chunks = self.client._split_message(
            raw, TelegramClient.MAX_MESSAGE_LENGTH // 2
        )
        for chunk in raw_chunks:
            converted = markdown_to_telegram_html(chunk)
            assert len(converted) <= TelegramClient.MAX_MESSAGE_LENGTH


def _make_response(status_code: int, json_data: dict) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


class TestSendMessage429Retry:
    """Tests for retrying a chunk when Telegram returns 429."""

    def _client(self) -> TelegramClient:
        client = TelegramClient.__new__(TelegramClient)
        client.token = "test-token"
        client.base_url = "https://api.telegram.org/bottest-token"
        return client

    @pytest.mark.asyncio
    async def test_retries_chunk_after_429(self):
        client = self._client()
        resp_429 = _make_response(429, {"ok": False, "parameters": {"retry_after": 2}})
        resp_200 = _make_response(200, {"ok": True, "result": {"message_id": 42}})
        mock_post = AsyncMock(side_effect=[resp_429, resp_200])
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with (
            patch("app.core.telegram_client.httpx.AsyncClient") as mock_client,
            patch("app.core.telegram_client.asyncio.sleep", side_effect=fake_sleep),
        ):
            mock_client.return_value.__aenter__.return_value.post = mock_post
            success, message_id = await client.send_message(1, "hi")

        assert success is True
        assert message_id == 42
        assert mock_post.call_count == 2
        assert sleeps == [2.0]

    @pytest.mark.asyncio
    async def test_gives_up_after_bounded_429_retries(self):
        client = self._client()
        resp_429 = _make_response(429, {"ok": False})  # no retry_after → default
        mock_post = AsyncMock(return_value=resp_429)
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with (
            patch("app.core.telegram_client.httpx.AsyncClient") as mock_client,
            patch("app.core.telegram_client.asyncio.sleep", side_effect=fake_sleep),
        ):
            mock_client.return_value.__aenter__.return_value.post = mock_post
            success, message_id = await client.send_message(1, "hi")

        assert success is False
        assert message_id is None
        assert mock_post.call_count == 3
        assert sleeps == [1.0, 1.0]
