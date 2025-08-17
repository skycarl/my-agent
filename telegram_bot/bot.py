"""
Telegram bot implementation using python-telegram-bot library.
"""

# Removed List import - no longer using message list types

import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from app.core.settings import config
from app.core.logger import init_logging

# Initialize logging
init_logging()


class TelegramMessage(BaseModel):
    """Pydantic model for telegram message validation."""

    message_id: int
    chat_id: int
    text: str
    user_id: int
    username: str | None = None


# API classes removed - using simple dict format for fire-and-forget calls


class TelegramBot:
    """Main Telegram bot class."""

    def __init__(self):
        self.token = config.telegram_bot_token
        self.app_url = config.app_url
        self.x_token = config.x_token
        self.authorized_user_id = config.authorized_user_id
        self.max_conversation_history = config.max_conversation_history
        self.selected_model: str = config.default_model
        self.application: Application | None = None

        # Note: Conversation history is now managed by the backend in persistent storage

        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables")
            raise ValueError("TELEGRAM_BOT_TOKEN must be set in environment variables")

        if not self.authorized_user_id:
            logger.error("AUTHORIZED_USER_ID is not set in environment variables")
            raise ValueError("AUTHORIZED_USER_ID must be set in environment variables")

        logger.info(
            f"TelegramBot initialized successfully with authorized user ID: {self.authorized_user_id}"
        )

    def _is_authorized_user(self, user_id: int) -> bool:
        """Check if the user is authorized to use the bot."""
        return user_id == self.authorized_user_id

    async def _notify_admin_unauthorized_access(
        self, update: Update, action: str = "message"
    ) -> None:
        """Send notification to admin about unauthorized access attempt."""
        if not self.application or not self.application.bot:
            logger.warning(
                "Cannot send admin notification: bot application not available"
            )
            return

        if not update.message or not update.message.from_user:
            logger.warning(
                "Cannot send admin notification: incomplete user information"
            )
            return

        try:
            user = update.message.from_user
            chat = update.message.chat

            # Format the notification message
            notification_text = (
                f"🚨 **UNAUTHORIZED ACCESS ATTEMPT** 🚨\n\n"
                f"**Action:** {action.upper()}\n"
                f"**User ID:** `{user.id}`\n"
                f"**Username:** @{user.username or 'N/A'}\n"
                f"**Name:** {user.first_name or ''} {user.last_name or ''}".strip()
                + "\n"
                f"**Chat ID:** `{chat.id}`\n"
                f"**Chat Type:** {chat.type}\n"
                f"**Message:** `{update.message.text or 'N/A'}`\n"
                f"**Date:** {update.message.date}\n"
                f"**Message ID:** `{update.message.message_id}`"
            )

            # Send notification to admin
            await self.application.bot.send_message(
                chat_id=self.authorized_user_id,
                text=notification_text,
                parse_mode="Markdown",
            )

            logger.info(
                f"Admin notification sent for unauthorized access by user {user.id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to send admin notification for unauthorized access: {e}"
            )

    async def _log_unauthorized_access(
        self, update: Update, action: str = "message"
    ) -> None:
        """Log detailed information about unauthorized access attempts and notify admin."""
        if not update.message or not update.message.from_user:
            logger.warning(
                f"Unauthorized {action} attempt with incomplete user information"
            )
            return

        user = update.message.from_user
        chat = update.message.chat

        logger.warning(
            f"UNAUTHORIZED ACCESS ATTEMPT - {action.upper()}: "
            f"User ID: {user.id}, "
            f"Username: {user.username}, "
            f"First Name: {user.first_name}, "
            f"Last Name: {user.last_name}, "
            f"Chat ID: {chat.id}, "
            f"Chat Type: {chat.type}, "
            f"Message: '{update.message.text}', "
            f"Message ID: {update.message.message_id}, "
            f"Date: {update.message.date}"
        )

        # Send notification to admin
        await self._notify_admin_unauthorized_access(update, action)

    # Conversation history methods removed - now managed by backend

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        if not update.message or not update.message.from_user:
            logger.warning("Received /start command without user information")
            return

        user_id = update.message.from_user.id

        # Check authorization
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "start command")
            return  # Silently ignore unauthorized users

        username = update.message.from_user.username
        logger.info(f"Authorized user {user_id} ({username}) started the bot")

        await update.message.reply_text(
            "Hello! I'm your AI assistant bot. Send me a message and I'll respond using AI!"
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        if not update.message or not update.message.from_user:
            logger.warning("Received /help command without user information")
            return

        user_id = update.message.from_user.id

        # Check authorization
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "help command")
            return  # Silently ignore unauthorized users

        username = update.message.from_user.username
        logger.info(f"Authorized user {user_id} ({username}) requested help")

        help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
/clear - Clear conversation history and start fresh
/model - Select the OpenAI model to use

Just send me any message and I'll respond using AI!
        """
        await update.message.reply_text(help_text)

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /clear command."""
        if not update.message or not update.message.from_user:
            logger.warning("Received /clear command without user information")
            return

        user_id = update.message.from_user.id

        # Check authorization
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "clear command")
            return  # Silently ignore unauthorized users

        username = update.message.from_user.username
        logger.info(
            f"Authorized user {user_id} ({username}) requested conversation clear"
        )

        # Clear the conversation history via backend API
        try:
            headers = {"Content-Type": "application/json", "X-Token": self.x_token}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.app_url}/clear_conversation",
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    await update.message.reply_text(
                        "✅ Conversation history cleared! Starting fresh."
                    )
                    logger.info(
                        f"Successfully cleared conversation history for user {user_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to clear conversation history: {response.status_code}"
                    )
                    await update.message.reply_text(
                        "❌ Failed to clear conversation history. Please try again."
                    )
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            await update.message.reply_text(
                "❌ Failed to clear conversation history. Please try again."
            )

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages."""
        if not update.message or not update.message.from_user:
            logger.warning("Received message without user information")
            return

        user_id = update.message.from_user.id

        # Check authorization first
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "message")
            return  # Silently ignore unauthorized users

        try:
            # Validate and extract message data
            message_data = TelegramMessage(
                message_id=update.message.message_id,
                chat_id=update.message.chat_id,
                text=update.message.text,
                user_id=update.message.from_user.id,
                username=update.message.from_user.username,
            )

            logger.debug(
                f"Processing message from authorized user {message_data.user_id} ({message_data.username}): {message_data.text}"
            )

            # Send typing action for a few seconds to show bot is processing
            await context.bot.send_chat_action(
                chat_id=message_data.chat_id, action="typing"
            )

            # Make fire-and-forget API call to backend (async processing)
            await self.send_message_to_backend(message_data.text)

            logger.debug(
                f"Sent message to backend for async processing: {message_data.text}"
            )

        except ValidationError as e:
            logger.info(f"Message validation error from authorized user {user_id}: {e}")
            await update.message.reply_text(
                "Sorry, there was an error processing your message."
            )
        except Exception as e:
            logger.info(f"Error handling message from authorized user {user_id}: {e}")
            await update.message.reply_text(
                "Sorry, something went wrong. Please try again."
            )

    async def send_message_to_backend(self, message: str) -> None:
        """Send message to backend for async processing (fire-and-forget)."""
        try:
            # Prepare the request with single input message
            api_request = {"input": message, "model": self.selected_model}

            headers = {"Content-Type": "application/json", "X-Token": self.x_token}

            logger.debug(
                f"Making fire-and-forget API call to {self.app_url}/agent_response"
            )

            # Make the API call without waiting for response processing
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.app_url}/agent_response",
                    json=api_request,
                    headers=headers,
                    timeout=1.0,  # Very short timeout; we don't wait for backend processing
                )

                if response.status_code == 200:
                    response_data = response.json()
                    logger.debug(
                        f"Backend accepted message for processing: {response_data}"
                    )
                else:
                    logger.warning(
                        f"Backend failed to accept message: {response.status_code} - {response.text}"
                    )

        except httpx.TimeoutException:
            # Fire-and-forget: silently ignore backend timeouts
            pass
        except Exception as e:
            logger.error(f"Error sending message to backend: {e}")
            # Note: We don't re-raise here since this is fire-and-forget

    async def set_model_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /model command to show model selection interface."""
        if not update.message or not update.message.from_user:
            logger.warning("Received /model command without user information")
            return

        user_id = update.message.from_user.id

        # Authorization check
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "model command")
            return  # Silently ignore unauthorized users

        try:
            # Get available models from API
            available_models = await self._get_available_models()

            if not available_models:
                await update.message.reply_text(
                    "❌ Failed to fetch available models. Please try again."
                )
                return

            # Create inline keyboard with model buttons (3 wide)
            keyboard = []
            row = []

            for i, model in enumerate(available_models):
                # Add checkmark if this is the current model
                button_text = f"✅ {model}" if model == self.selected_model else model
                row.append(
                    InlineKeyboardButton(button_text, callback_data=f"model_{model}")
                )

                # Start new row every 3 buttons
                if (i + 1) % 3 == 0:
                    keyboard.append(row)
                    row = []

            # Add remaining buttons if any
            if row:
                keyboard.append(row)

            reply_markup = InlineKeyboardMarkup(keyboard)

            message_text = (
                f"🤖 Current model: **{self.selected_model}**\n\nSelect a model to use:"
            )

            await update.message.reply_text(
                message_text, reply_markup=reply_markup, parse_mode="Markdown"
            )

            logger.info(
                f"Authorized user {user_id} requested model selection interface"
            )

        except Exception as e:
            logger.warning(f"Failed to show model selection interface: {e}")
            await update.message.reply_text(
                "❌ Failed to load model options. Please try again."
            )

    async def _get_available_models(self) -> list[str]:
        """Get available models from the API."""
        try:
            headers = {"X-Token": self.x_token}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.app_url}/models", headers=headers, timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if isinstance(models, list):
                        return [str(model) for model in models]
                    return []
                else:
                    logger.warning(f"Failed to get models: {response.status_code}")
                    return []

        except Exception as e:
            logger.warning(f"Error getting available models: {e}")
            return []

    async def model_callback_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle model selection button callbacks."""
        if not update.callback_query or not update.callback_query.from_user:
            logger.warning("Received model callback without user information")
            return

        user_id = update.callback_query.from_user.id

        # Authorization check
        if not self._is_authorized_user(user_id):
            await self._log_unauthorized_access(update, "model callback")
            return  # Silently ignore unauthorized users

        try:
            # Extract model name from callback data
            callback_data = update.callback_query.data
            if not callback_data or not callback_data.startswith("model_"):
                logger.warning(f"Invalid callback data: {callback_data}")
                return

            selected_model = callback_data[6:]  # Remove "model_" prefix

            # Validate the model by fetching available models from API
            available_models = await self._get_available_models()
            if selected_model not in available_models:
                await update.callback_query.answer("❌ Invalid model selected")
                return

            # Update the selected model
            self.selected_model = selected_model
            logger.info(f"Authorized user {user_id} set model to {selected_model}")

            # Answer the callback query
            await update.callback_query.answer(f"✅ Model set to {selected_model}")

            # Update the message to show the new selection
            try:
                # Get available models again for the updated keyboard
                available_models = await self._get_available_models()

                # Create updated inline keyboard
                keyboard = []
                row = []

                for i, model in enumerate(available_models):
                    # Add checkmark if this is the current model
                    button_text = (
                        f"✅ {model}" if model == self.selected_model else model
                    )
                    row.append(
                        InlineKeyboardButton(
                            button_text, callback_data=f"model_{model}"
                        )
                    )

                    # Start new row every 3 buttons
                    if (i + 1) % 3 == 0:
                        keyboard.append(row)
                        row = []

                # Add remaining buttons if any
                if row:
                    keyboard.append(row)

                reply_markup = InlineKeyboardMarkup(keyboard)

                message_text = f"🤖 Current model: **{self.selected_model}**\n\nSelect a model to use:"

                await update.callback_query.edit_message_text(
                    message_text, reply_markup=reply_markup, parse_mode="Markdown"
                )

            except Exception as e:
                logger.warning(f"Failed to update message after model selection: {e}")
                # If we can't update the message, at least answer the callback
                await update.callback_query.answer(f"✅ Model set to {selected_model}")

        except Exception as e:
            logger.warning(f"Error handling model callback: {e}")
            await update.callback_query.answer(
                "❌ Failed to set model. Please try again."
            )

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors."""
        logger.error(f"Bot error occurred: {context.error}")
        if update:
            logger.error(f"Update that caused error: {update}")

    def setup_handlers(self):
        """Set up bot handlers."""
        if not self.application:
            raise RuntimeError("Application not initialized")

        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("model", self.set_model_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(CallbackQueryHandler(self.model_callback_handler))
        self.application.add_error_handler(self.error_handler)
        logger.info("Bot handlers set up successfully")

    def run(self):
        """Run the bot using polling."""
        logger.info("Starting Telegram bot...")

        # Create application
        self.application = Application.builder().token(self.token).build()

        # Set up handlers
        self.setup_handlers()

        # Start polling with drop_pending_updates=True
        logger.info("Telegram bot is running and polling for messages...")
        self.application.run_polling(drop_pending_updates=True)


def main():
    """Main function to run the bot."""
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    main()
