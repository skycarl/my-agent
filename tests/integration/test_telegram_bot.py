"""
Tests for the Telegram bot module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from telegram_bot.bot import TelegramMessage, TelegramBot


def make_update(
    user_id=123,
    chat_id=123,
    chat_type="private",
    is_bot=False,
    username="testuser",
    text=None,
):
    """Build a mock Update with both message.* and effective_* populated."""
    update = Mock()
    update.message.reply_text = AsyncMock()
    update.message.from_user.id = user_id
    update.message.from_user.username = username
    update.message.chat_id = chat_id
    if text is not None:
        update.message.text = text
    update.effective_message = update.message
    update.effective_user.id = user_id
    update.effective_user.is_bot = is_bot
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    return update


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


# APIMessage and APIRequest classes removed - using simple dict format for fire-and-forget calls


class TestTelegramBot:
    """Test TelegramBot class."""

    @pytest.fixture(autouse=True)
    def _allowlist(self):
        """Treat user 123 as authorized for all bot tests."""
        import telegram_bot.bot as bot_module

        bot_module._last_unauthorized_notify.clear()
        with patch(
            "telegram_bot.bot.access_control.is_authorized",
            side_effect=lambda user_id, chat_id, chat_type: user_id == 123,
        ):
            yield

    @staticmethod
    def _base_config(mock_config):
        mock_config.telegram_bot_token = "test_token"
        mock_config.app_url = "http://localhost:8000"
        mock_config.x_token = "test_x_token"
        mock_config.max_conversation_history = 10
        mock_config.owner_user_id = 123
        mock_config.default_model = "gpt-5"

    def test_bot_initialization_without_token(self):
        """Test bot initialization fails without token."""
        with patch("telegram_bot.bot.config") as mock_config:
            mock_config.telegram_bot_token = ""

            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN must be set"):
                TelegramBot()

    def test_bot_initialization_with_token(self):
        """Test bot initialization with token."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()
            assert bot.token == "test_token"
            assert bot.app_url == "http://localhost:8000"
            assert bot.x_token == "test_x_token"
            assert bot.max_conversation_history == 10
            assert bot.owner_user_id == 123

    @pytest.mark.asyncio
    async def test_start_command(self):
        """Test /start command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()
            mock_update = make_update()
            mock_context = Mock()

            await bot.start_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Hello! I'm your AI assistant bot" in call_args

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test /help command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()
            mock_update = make_update()
            mock_context = Mock()

            await bot.help_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Available commands:" in call_args

    @pytest.mark.asyncio
    async def test_send_message_to_backend_success(self):
        """Test successful message sending to backend."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "message": "Message processed",
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                # Should not raise any exceptions (fire-and-forget)
                await bot.send_message_to_backend("Hello", conversation_id="123")

                # Verify the API call was made and carried the conversation_id
                mock_post.assert_called_once()
                sent = mock_post.call_args.kwargs["json"]
                assert sent["conversation_id"] == "123"
                assert sent["input"] == "Hello"

    @pytest.mark.asyncio
    async def test_send_message_to_backend_api_error(self):
        """A fast non-200 from the backend raises so the handler can tell the user."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            # Mock API error response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Server error"

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # A response that fast means the backend actively rejected the
                # request — the bot raises so handle_message replies with an error
                with pytest.raises(RuntimeError, match="status 500"):
                    await bot.send_message_to_backend("Hello", conversation_id="123")

                # Verify the API call was made
                mock_client.return_value.__aenter__.return_value.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_to_backend_read_timeout_is_fire_and_forget(self):
        """Read timeouts are expected (the backend keeps processing) and don't raise."""
        import httpx

        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.ReadTimeout("timed out")
                )

                # Should not raise — the reply arrives via Telegram later
                await bot.send_message_to_backend("Hello", conversation_id="123")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_type",
        ["ConnectTimeout", "WriteTimeout", "ConnectError"],
    )
    async def test_send_message_to_backend_unreachable_raises(self, exception_type):
        """Timeouts that mean the request never arrived raise like ConnectError."""
        import httpx

        exception_class = getattr(httpx, exception_type)

        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=exception_class("backend unreachable")
                )

                with pytest.raises(exception_class):
                    await bot.send_message_to_backend("Hello", conversation_id="123")

    @pytest.mark.asyncio
    async def test_clear_command(self):
        """Test /clear command handler."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            # Mock successful backend response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                mock_update = make_update(chat_id=456)
                mock_context = Mock()

                await bot.clear_command(mock_update, mock_context)

                # Verify backend API was called with the conversation_id
                mock_post.assert_called_once()
                assert mock_post.call_args.kwargs["json"] == {"conversation_id": "456"}

                # Verify success reply was sent
                mock_update.message.reply_text.assert_called_once_with(
                    "✅ Conversation history cleared! Starting fresh."
                )

    @pytest.mark.asyncio
    async def test_set_model_command(self):
        """Test /model command shows model selection interface."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            # Mock API response for available models
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": ["gpt-5-mini", "gpt-5"],
                "default_model": "gpt-5",
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                bot = TelegramBot()

                mock_update = make_update(text="/model")
                mock_context = Mock()
                mock_context.args = []

                await bot.set_model_command(mock_update, mock_context)

                # Should not change the model directly, just show interface
                assert bot._get_model(123) == "gpt-5"  # Default unchanged
                mock_update.message.reply_text.assert_called_once()
                call_args = mock_update.message.reply_text.call_args[0][0]
                assert "Current model" in call_args
                assert "Select a model to use" in call_args

    @pytest.mark.asyncio
    async def test_set_model_command_with_api_failure(self):
        """Test /model command when API fails to return models."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            # Mock API failure
            mock_response = Mock()
            mock_response.status_code = 500

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                mock_update = make_update(text="/model")
                mock_context = Mock()
                mock_context.args = []

                await bot.set_model_command(mock_update, mock_context)

                # Should not change the model
                assert bot._get_model(123) == "gpt-5"  # Default
                mock_update.message.reply_text.assert_called_once()
                call_args = mock_update.message.reply_text.call_args[0][0]
                assert "Failed to fetch available models" in call_args

    @pytest.mark.asyncio
    async def test_get_available_models_success(self):
        """Test successful API call to get available models."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": ["gpt-5-mini", "gpt-5"],
                "default_model": "gpt-5",
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                models = await bot._get_available_models()
                assert models == ["gpt-5-mini", "gpt-5"]

    @pytest.mark.asyncio
    async def test_get_available_models_failure(self):
        """Test API call failure when getting available models."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

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

    @pytest.mark.asyncio
    async def test_model_callback_sets_model_per_chat(self):
        """Selecting a model in one chat must not change other chats' models."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            mock_update = make_update(chat_id=456)
            mock_update.callback_query.from_user.id = 123
            mock_update.callback_query.data = "model_gpt-5-mini"
            mock_update.callback_query.answer = AsyncMock()
            mock_update.callback_query.edit_message_text = AsyncMock()

            with patch.object(
                bot,
                "_get_available_models",
                AsyncMock(return_value=["gpt-5-mini", "gpt-5"]),
            ):
                await bot.model_callback_handler(mock_update, Mock())

            assert bot._get_model(456) == "gpt-5-mini"
            # Other chats (e.g. the owner's private chat) keep the default
            assert bot._get_model(999) == "gpt-5"

    @pytest.mark.asyncio
    async def test_send_message_to_backend_uses_per_chat_model(self):
        """The payload model comes from the chat's selection, not a global."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()
            bot.selected_models["456"] = "gpt-5-mini"

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}

            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value.post = mock_post

                await bot.send_message_to_backend("Hello", conversation_id="456")
                assert mock_post.call_args.kwargs["json"]["model"] == "gpt-5-mini"

                await bot.send_message_to_backend("Hello", conversation_id="123")
                assert mock_post.call_args.kwargs["json"]["model"] == "gpt-5"

    @pytest.mark.asyncio
    async def test_unauthorized_notifications_throttled_per_user(self):
        """Repeated unauthorized attempts DM the owner at most once per user."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()
            bot.application = Mock()
            bot.application.bot.send_message = AsyncMock()

            mock_update = make_update(user_id=999, username="hacker", text="spam")

            for _ in range(3):
                await bot._log_unauthorized_access(mock_update, "message")

            assert bot.application.bot.send_message.await_count == 1

            # A different offender still triggers a notification
            other_update = make_update(user_id=888, username="other", text="spam")
            await bot._log_unauthorized_access(other_update, "message")
            assert bot.application.bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_version_command_with_env_vars(self):
        """Test /version command when git info is set via config."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)
            mock_config.git_commit = "abc1234567890"
            mock_config.git_commit_message = "feat: add cool feature"

            bot = TelegramBot()

            mock_update = make_update()
            mock_context = Mock()

            with patch("telegram_bot.bot.pkg_version", return_value="0.10.1"):
                await bot.version_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "0.10.1" in call_args
            assert "abc1234" in call_args
            assert "feat: add cool feature" in call_args

    @pytest.mark.asyncio
    async def test_version_command_falls_back_to_git(self):
        """Test /version command falls back to git subprocess when env vars are empty."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)
            mock_config.git_commit = ""
            mock_config.git_commit_message = ""

            bot = TelegramBot()

            mock_update = make_update()
            mock_context = Mock()

            with (
                patch("telegram_bot.bot.pkg_version", return_value="0.10.1"),
                patch(
                    "subprocess.check_output",
                    side_effect=["deadbeef12345\n", "fix: a bug\n"],
                ),
            ):
                await bot.version_command(mock_update, mock_context)

            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "0.10.1" in call_args
            assert "deadbee" in call_args
            assert "fix: a bug" in call_args

    @pytest.mark.asyncio
    async def test_version_command_unauthorized(self):
        """Test /version command rejects unauthorized users."""
        with patch("telegram_bot.bot.config") as mock_config:
            self._base_config(mock_config)

            bot = TelegramBot()

            mock_update = make_update(user_id=999, username="hacker")
            mock_context = Mock()

            await bot.version_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_not_called()
