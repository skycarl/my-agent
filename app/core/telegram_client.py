"""
Telegram client helper for sending messages from the FastAPI application.

This module provides a way for the FastAPI app to send messages to Telegram users
without needing to run the full Telegram bot.
"""

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

    # Code blocks (``` ... ```) — must come before inline code
    text = re.sub(
        r"```(?:\w*)\n?(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code (`code`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bullet list markers (- item or * item at start of line) → bullet character
    # Must run before italic conversion so "* item" isn't treated as italic
    text = re.sub(r"^[-*] ", "• ", text, flags=re.MULTILINE)

    # Bold (**text**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic (*text*) — only single *, not inside bold
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)

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

            # Try to split at a newline within the limit
            split_pos = remaining.rfind("\n", 0, self.MAX_MESSAGE_LENGTH)
            if split_pos == -1:
                # No newline found, try a space
                split_pos = remaining.rfind(" ", 0, self.MAX_MESSAGE_LENGTH)
            if split_pos == -1:
                # No good break point, hard cut
                split_pos = self.MAX_MESSAGE_LENGTH

            chunks.append(remaining[:split_pos])
            remaining = remaining[split_pos:].lstrip("\n")

        return chunks

    async def send_message(
        self, user_id: int, message: str, parse_mode: Optional[str] = None
    ) -> Tuple[bool, Optional[int]]:
        """
        Send a message to a Telegram user.

        Messages exceeding Telegram's 4096-character limit are automatically
        split into multiple messages.

        Args:
            user_id: Telegram user ID to send the message to
            message: Message text to send
            parse_mode: Optional parse mode (e.g., 'Markdown', 'HTML')

        Returns:
            Tuple of (success: bool, message_id: Optional[int]) where message_id
            is from the last successfully sent chunk.
        """
        try:
            self.validate_configuration()

            chunks = self._split_message(message)
            if len(chunks) > 1:
                logger.debug(
                    f"Message too long ({len(message)} chars), split into {len(chunks)} chunks"
                )

            last_message_id = None

            async with httpx.AsyncClient() as client:
                for i, chunk in enumerate(chunks):
                    payload = {"chat_id": user_id, "text": chunk}
                    if parse_mode:
                        payload["parse_mode"] = parse_mode

                    logger.debug(
                        f"Sending Telegram message to user {user_id}"
                        + (f" (chunk {i + 1}/{len(chunks)})" if len(chunks) > 1 else "")
                    )

                    response = await client.post(
                        f"{self.base_url}/sendMessage", json=payload, timeout=30.0
                    )

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

    async def send_message_with_retry(
        self,
        user_id: int,
        message: str,
        parse_mode: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5,
    ) -> Tuple[bool, Optional[int]]:
        """
        Send a message with retry logic.

        Args:
            user_id: Telegram user ID to send the message to
            message: Message text to send
            parse_mode: Optional parse mode (e.g., 'Markdown', 'HTML')
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            Tuple of (success: bool, message_id: Optional[int])
        """
        import asyncio

        for attempt in range(max_retries + 1):
            success, message_id = await self.send_message(user_id, message, parse_mode)

            if success:
                return True, message_id

            if attempt < max_retries:
                logger.debug(
                    f"Telegram message send attempt {attempt + 1} failed, retrying in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"Failed to send Telegram message to user {user_id} after {max_retries + 1} attempts"
                )

        return False, None

    async def test_connection(self) -> bool:
        """
        Test the Telegram bot connection by getting bot info.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            self.validate_configuration()

            logger.debug("Testing Telegram bot connection...")

            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/getMe", timeout=10.0)

                if response.status_code == 200:
                    response_data = response.json()

                    if response_data.get("ok"):
                        bot_info = response_data.get("result", {})
                        bot_name = bot_info.get("first_name", "Unknown")
                        bot_username = bot_info.get("username", "Unknown")
                        logger.info(
                            f"Telegram bot connection successful - Bot: {bot_name} (@{bot_username})"
                        )
                        return True
                    else:
                        error_description = response_data.get(
                            "description", "Unknown error"
                        )
                        logger.error(f"Telegram bot API error: {error_description}")
                        return False
                else:
                    logger.error(
                        f"Telegram bot connection failed with status {response.status_code}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error testing Telegram bot connection: {str(e)}")
            return False


# Create a global Telegram client instance
telegram_client = TelegramClient()
