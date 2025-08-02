"""
Telegram client helper for sending messages from the FastAPI application.

This module provides a way for the FastAPI app to send messages to Telegram users
without needing to run the full Telegram bot.
"""

import httpx
from typing import Optional, Tuple
from loguru import logger

from app.core.settings import config


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

    async def send_message(
        self, user_id: int, message: str, parse_mode: Optional[str] = None
    ) -> Tuple[bool, Optional[int]]:
        """
        Send a message to a Telegram user.

        Args:
            user_id: Telegram user ID to send the message to
            message: Message text to send
            parse_mode: Optional parse mode (e.g., 'Markdown', 'HTML')

        Returns:
            Tuple of (success: bool, message_id: Optional[int])
        """
        try:
            self.validate_configuration()

            # Prepare the request payload
            payload = {"chat_id": user_id, "text": message}

            if parse_mode:
                payload["parse_mode"] = parse_mode

            logger.debug(f"Sending Telegram message to user {user_id}")

            # Make the API call to Telegram
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage", json=payload, timeout=30.0
                )

                if response.status_code == 200:
                    response_data = response.json()

                    if response_data.get("ok"):
                        message_id = response_data.get("result", {}).get("message_id")
                        logger.debug(
                            f"Successfully sent Telegram message to user {user_id}, message_id: {message_id}"
                        )
                        return True, message_id
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
