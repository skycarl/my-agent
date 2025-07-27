"""
Tests for the Telegram bot module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from telegram_bot.bot import TelegramMessage, APIMessage, APIRequest, TelegramBot


class TestTelegramMessage:
    """Test TelegramMessage pydantic model."""

    def test_valid_message(self):
        """Test creating a valid telegram message."""
        message = TelegramMessage(
            message_id=123,
            chat_id=456,
            text="Hello, world!",
            user_id=789,
            username="testuser",
        )

        assert message.message_id == 123
        assert message.chat_id == 456
        assert message.text == "Hello, world!"
        assert message.user_id == 789
        assert message.username == "testuser"

    def test_message_without_username(self):
        """Test creating a message without username."""
        message = TelegramMessage(
            message_id=123,
            chat_id=456,
            text="Hello, world!",
            user_id=789,
        )

        assert message.message_id == 123
        assert message.chat_id == 456
        assert message.text == "Hello, world!"
        assert message.user_id == 789
        assert message.username is None


class TestAPIMessage:
    """Test APIMessage pydantic model."""

    def test_valid_api_message(self):
        """Test creating a valid API message."""
        message = APIMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"


class TestAPIRequest:
    """Test APIRequest pydantic model."""

    def test_valid_api_request(self):
        """Test creating a valid API request."""
        messages = [
            APIMessage(role="user", content="Hello"),
            APIMessage(role="assistant", content="Hi there!"),
        ]
        request = APIRequest(messages=messages)

        assert len(request.messages) == 2
        assert request.messages[0].role == "user"
        assert request.messages[1].role == "assistant"


class TestTelegramBot:
    """Test TelegramBot class."""

    def test_bot_initialization_without_token(self):
        """Test bot initialization fails without token."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = ""

            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN must be set"):
                TelegramBot()

    def test_bot_initialization_with_token(self):
        """Test bot initialization with token."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()
            assert bot.token == "test_token"
            assert bot.app_url == "http://localhost:8000"
            assert bot.x_token == "test_x_token"
            assert bot.max_conversation_history == 10
            assert bot.authorized_user_id == 123

    @pytest.mark.asyncio
    async def test_start_command(self):
        """Test /start command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock update and context
            mock_update = Mock()
            mock_update.message.reply_text = AsyncMock()
            mock_update.message.from_user.id = 123  # Set authorized user ID
            mock_update.message.from_user.username = "testuser"
            mock_context = Mock()

            await bot.start_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Hello! I'm your AI assistant bot" in call_args

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test /help command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock update and context
            mock_update = Mock()
            mock_update.message.reply_text = AsyncMock()
            mock_update.message.from_user.id = 123  # Set authorized user ID
            mock_update.message.from_user.username = "testuser"
            mock_context = Mock()

            await bot.help_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Available commands:" in call_args

    @pytest.mark.asyncio
    async def test_get_ai_response_success(self):
        """Test successful AI response."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": "AI response here"}

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                conversation_history = [APIMessage(role="user", content="Hello")]
                response = await bot.get_ai_response(conversation_history)

                assert response == "AI response here"

    @pytest.mark.asyncio
    async def test_get_ai_response_api_error(self):
        """Test API error handling."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock API error response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Server error"

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                conversation_history = [APIMessage(role="user", content="Hello")]
                response = await bot.get_ai_response(conversation_history)

                assert "trouble connecting" in response

    def test_conversation_history_management(self):
        """Test conversation history management."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 3
            mock_config.authorized_user_id = 123

            bot = TelegramBot()
            user_id = 123

            # Test adding messages
            bot._add_message_to_history(user_id, "user", "Hello")
            bot._add_message_to_history(user_id, "assistant", "Hi there!")

            history = bot._get_conversation_history(user_id)
            assert len(history) == 2
            assert history[0].role == "user"
            assert history[0].content == "Hello"
            assert history[1].role == "assistant"
            assert history[1].content == "Hi there!"

            # Test conversation truncation
            bot._add_message_to_history(user_id, "user", "Message 3")
            bot._add_message_to_history(user_id, "assistant", "Response 3")

            history = bot._get_conversation_history(user_id)
            assert len(history) == 3  # Should be truncated to max_conversation_history
            assert (
                history[0].role == "assistant"
            )  # Should keep the most recent messages
            assert history[0].content == "Hi there!"

            # Test clearing history
            bot._clear_conversation_history(user_id)
            history = bot._get_conversation_history(user_id)
            assert len(history) == 0

    @pytest.mark.asyncio
    async def test_clear_command(self):
        """Test /clear command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Add some conversation history
            user_id = 123
            bot._add_message_to_history(user_id, "user", "Hello")
            bot._add_message_to_history(user_id, "assistant", "Hi there!")

            # Verify history exists
            history = bot._get_conversation_history(user_id)
            assert len(history) == 2

            # Mock update and context
            mock_update = Mock()
            mock_update.message.reply_text = AsyncMock()
            mock_update.message.from_user.id = 123  # Set authorized user ID
            mock_update.message.from_user.username = "testuser"
            mock_context = Mock()

            await bot.clear_command(mock_update, mock_context)

            # Verify response was sent
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Conversation history cleared" in call_args

            # Verify history was cleared
            history = bot._get_conversation_history(user_id)
            assert len(history) == 0

    @pytest.mark.asyncio
    async def test_set_model_command(self):
        """Test /model command shows model selection interface."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            # Mock API response for available models
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": ["gpt-4o", "gpt-4o-mini"],
                "default_model": "gpt-4o",
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                bot = TelegramBot()

                # Mock update and context
                mock_update = Mock()
                mock_update.message.reply_text = AsyncMock()
                mock_update.message.from_user.id = 123
                mock_update.message.from_user.username = "testuser"
                mock_update.message.text = "/model"

                mock_context = Mock()
                mock_context.args = []

                await bot.set_model_command(mock_update, mock_context)

                # Should not change the model directly, just show interface
                assert bot.selected_model == "gpt-4o"  # Default unchanged
                mock_update.message.reply_text.assert_called_once()
                call_args = mock_update.message.reply_text.call_args[0][0]
                assert "Current model" in call_args
                assert "Select a model to use" in call_args

    @pytest.mark.asyncio
    async def test_set_model_command_with_api_failure(self):
        """Test /model command when API fails to return models."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock API failure
            mock_response = Mock()
            mock_response.status_code = 500

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                # Mock update and context
                mock_update = Mock()
                mock_update.message.reply_text = AsyncMock()
                mock_update.message.from_user.id = 123
                mock_update.message.from_user.username = "testuser"
                mock_update.message.text = "/model"

                mock_context = Mock()
                mock_context.args = []

                await bot.set_model_command(mock_update, mock_context)

                # Should not change the model
                assert bot.selected_model == "gpt-4o"  # Default
                mock_update.message.reply_text.assert_called_once()
                call_args = mock_update.message.reply_text.call_args[0][0]
                assert "Failed to fetch available models" in call_args

    @pytest.mark.asyncio
    async def test_get_available_models_success(self):
        """Test successful API call to get available models."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": ["gpt-4o", "gpt-4o-mini"],
                "default_model": "gpt-4o",
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                models = await bot._get_available_models()
                assert models == ["gpt-4o", "gpt-4o-mini"]

    @pytest.mark.asyncio
    async def test_get_available_models_failure(self):
        """Test API call failure when getting available models."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = "test_token"
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_x_token"
            mock_config.max_conversation_history = 10
            mock_config.authorized_user_id = 123

            bot = TelegramBot()

            # Mock API failure
            mock_response = Mock()
            mock_response.status_code = 500

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                models = await bot._get_available_models()
                assert models == []
