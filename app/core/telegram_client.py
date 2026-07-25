"""
Telegram client helper for sending messages from the FastAPI application.

This module provides a way for the FastAPI app to send messages to Telegram users
without needing to run the full Telegram bot.
"""

import asyncio
import html
import re

import httpx
from typing import Optional, Tuple
from loguru import logger

from app.core.settings import config


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown formatting from agent output to Telegram-compatible HTML.

    Handles: **bold**, *italic*, `inline code`, ```code blocks```, and list markers.
    Escapes HTML special characters first so agent output can't inject tags.
    """
    # First, escape HTML special characters so raw <, >, & in agent text are safe
    text = html.escape(text)

    # Extract code blocks and inline code into placeholders so the formatting
    # regexes below can't inject tags inside <pre>/<code> — Telegram forbids
    # nested entities there and rejects the whole message with a 400.
    placeholders: list[str] = []

    def _stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    # Code blocks (``` ... ```) — must come before inline code
    text = re.sub(
        r"```(?:\w*)\n?(.*?)```",
        lambda m: _stash(f"<pre>{m.group(1)}</pre>"),
        text,
        flags=re.DOTALL,
    )

    # Inline code (`code`)
    text = re.sub(r"`([^`]+)`", lambda m: _stash(f"<code>{m.group(1)}</code>"), text)

    # Markdown links [text](url) → <a href="url">text</a> so Telegram renders a
    # single tappable label instead of leaving the raw [text](url) to be
    # auto-linked as two separate ugly links. URLs were already HTML-escaped
    # above, which is what Telegram wants for href values (e.g. & → &amp;).
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    # Headings (#, ##, ... up to ######) → bold line. Telegram HTML has no
    # heading tag, so the literal "## " would otherwise show through.
    text = re.sub(r"^#{1,6} +(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Bullet list markers (- item or * item at start of line) → bullet character
    # Must run before italic conversion so "* item" isn't treated as italic
    text = re.sub(r"^[-*] ", "• ", text, flags=re.MULTILINE)

    # Bold (**text**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic (*text*) — only single *, not inside bold
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)

    # Restore code blocks and inline code
    text = re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)

    return text


class TelegramClient:
    """Telegram client for sending messages from the FastAPI application."""

    def __init__(self):
        """Initialize the Telegram client."""
        self.token = config.telegram_bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        logger.debug("Telegram client initialized")

    def is_configured(self) -> bool:
        """Check if Telegram bot token is configured."""
        configured = bool(self.token.strip())
        logger.debug(
            f"Telegram configuration check: {'configured' if configured else 'not configured'}"
        )
        return configured

    def validate_configuration(self) -> None:
        """Validate that Telegram is properly configured."""
        if not self.is_configured():
            logger.error("Telegram bot token is not configured")
            raise ValueError(
                "Telegram bot token is not configured. "
                "Please set the TELEGRAM_BOT_TOKEN environment variable."
            )
        logger.debug("Telegram configuration validated successfully")

    # Telegram API limit for message text
    MAX_MESSAGE_LENGTH = 4096

    def _split_message(self, message: str) -> list[str]:
        """Split a message into chunks that fit within Telegram's limit.

        Splits on newlines first, then on spaces, to avoid breaking mid-word.
        """
        if len(message) <= self.MAX_MESSAGE_LENGTH:
            return [message]

        chunks = []
        remaining = message
        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break

            # Try to split at a newline within the limit. A break point at
            # index 0 would produce an empty chunk and no progress (infinite
            # loop), so search from index 1.
            split_pos = remaining.rfind("\n", 1, self.MAX_MESSAGE_LENGTH)
            if split_pos <= 0:
                # No newline found, try a space
                split_pos = remaining.rfind(" ", 1, self.MAX_MESSAGE_LENGTH)
            if split_pos <= 0:
                # No good break point, hard cut
                split_pos = self.MAX_MESSAGE_LENGTH

            chunks.append(remaining[:split_pos])
            remaining = remaining[split_pos:].lstrip("\n ")

        return chunks

    async def send_message(
        self,
        user_id: int,
        message: str,
        parse_mode: Optional[str] = None,
        markdown: bool = False,
    ) -> Tuple[bool, Optional[int]]:
        """
        Send a message to a Telegram user.

        Messages exceeding Telegram's 4096-character limit are automatically
        split into multiple messages.

        Args:
            user_id: Telegram user ID to send the message to
            message: Message text to send
            parse_mode: Optional parse mode (e.g., 'Markdown', 'HTML')
            markdown: If True, message is raw markdown that will be split first,
                then each chunk converted to Telegram HTML independently.
                This avoids splitting in the middle of HTML tags.

        Returns:
            Tuple of (success: bool, message_id: Optional[int]) where message_id
            is from the last successfully sent chunk.
        """
        try:
            self.validate_configuration()

            if markdown:
                # Split raw markdown, then convert each chunk to HTML
                raw_chunks = self._split_message(message)
                chunks = [markdown_to_telegram_html(c) for c in raw_chunks]
                parse_mode = "HTML"
            else:
                chunks = self._split_message(message)

            if len(chunks) > 1:
                logger.debug(
                    f"Message too long ({len(message)} chars), split into {len(chunks)} chunks"
                )

            last_message_id = None

            async with httpx.AsyncClient() as client:
                for i, chunk in enumerate(chunks):
                    payload = {
                        "chat_id": user_id,
                        "text": chunk,
                        # Suppress the large link-preview card Telegram generates
                        # from the first URL in the message.
                        "disable_web_page_preview": True,
                    }
                    if parse_mode:
                        payload["parse_mode"] = parse_mode

                    logger.debug(
                        f"Sending Telegram message to user {user_id}"
                        + (f" (chunk {i + 1}/{len(chunks)})" if len(chunks) > 1 else "")
                    )

                    # Retry the same chunk on 429 (rate limited), honoring
                    # Telegram's retry_after, so multi-chunk sends aren't
                    # truncated mid-sequence.
                    for attempt in range(3):
                        response = await client.post(
                            f"{self.base_url}/sendMessage", json=payload, timeout=30.0
                        )
                        if response.status_code != 429 or attempt == 2:
                            break
                        try:
                            retry_after = float(
                                response.json()["parameters"]["retry_after"]
                            )
                        except (KeyError, TypeError, ValueError):
                            retry_after = 1.0
                        logger.warning(
                            f"Telegram rate limited (429) for user {user_id}, "
                            f"retrying chunk in {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)

                    if response.status_code == 200:
                        response_data = response.json()

                        if response_data.get("ok"):
                            last_message_id = response_data.get("result", {}).get(
                                "message_id"
                            )
                            logger.debug(
                                f"Successfully sent Telegram message to user {user_id}, message_id: {last_message_id}"
                            )
                        else:
                            error_description = response_data.get(
                                "description", "Unknown error"
                            )
                            logger.warning(
                                f"Telegram API returned error for user {user_id}: {error_description}"
                            )
                            return False, None
                    else:
                        logger.warning(
                            f"Telegram API returned status {response.status_code} for user {user_id}: {response.text}"
                        )
                        return False, None

            return True, last_message_id

        except Exception as e:
            logger.error(f"Error sending Telegram message to user {user_id}: {str(e)}")
            logger.debug(f"Telegram client error details: {e}", exc_info=True)
            return False, None


# Create a global Telegram client instance
telegram_client = TelegramClient()
