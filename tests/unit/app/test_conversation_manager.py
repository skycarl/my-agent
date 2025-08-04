"""
Tests for the conversation manager.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from app.core.conversation_manager import ConversationManager, ConversationMessage


class TestConversationMessage:
    """Test the ConversationMessage class."""

    def test_conversation_message_creation(self):
        """Test creating a conversation message."""
        message = ConversationMessage(
            role="user",
            content="Hello world",
            message_type="chat",
            message_id="msg_123",
        )

        assert message.role == "user"
        assert message.content == "Hello world"
        assert message.message_type == "chat"
        assert message.message_id == "msg_123"
        assert message.alert_id is None
        assert message.timestamp is not None

    def test_conversation_message_model_dump(self):
        """Test converting message to dictionary using Pydantic model_dump."""
        message = ConversationMessage(
            role="assistant",
            content="Hi there!",
            message_type="alert",
            alert_id="alert_456",
        )

        data = message.model_dump()

        assert data["role"] == "assistant"
        assert data["content"] == "Hi there!"
        assert data["message_type"] == "alert"
        assert data["alert_id"] == "alert_456"
        assert "timestamp" in data
        assert "message_id" in data  # Pydantic includes None fields by default

    def test_conversation_message_from_dict(self):
        """Test creating message from dictionary using Pydantic validation."""
        data = {
            "role": "user",
            "content": "Test message",
            "timestamp": "2024-01-01T12:00:00",
            "message_type": "chat",
            "message_id": "msg_789",
        }

        message = ConversationMessage.model_validate(data)

        assert message.role == "user"
        assert message.content == "Test message"
        assert message.timestamp == "2024-01-01T12:00:00"
        assert message.message_type == "chat"
        assert message.message_id == "msg_789"

    def test_conversation_message_defaults(self):
        """Test that Pydantic model uses correct default values."""
        message = ConversationMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"
        assert message.message_type == "chat"  # Default value
        assert message.message_id is None  # Default value
        assert message.alert_id is None  # Default value
        assert message.timestamp is not None  # Should be auto-generated


class TestConversationManager:
    """Test the ConversationManager class."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create a temporary storage directory."""
        return str(tmp_path)

    @pytest.fixture
    def conversation_manager(self, temp_storage):
        """Create a conversation manager with temp storage."""
        with patch("app.core.conversation_manager.config") as mock_config:
            mock_config.storage_path = temp_storage
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10
            return ConversationManager(temp_storage)

    def test_conversation_manager_initialization(self, temp_storage):
        """Test conversation manager initialization."""
        with patch("app.core.conversation_manager.config") as mock_config:
            mock_config.storage_path = temp_storage
            mock_config.authorized_user_id = 12345

            manager = ConversationManager(temp_storage)

            assert manager.storage_dir == Path(temp_storage)
            assert manager.user_id == 12345
            assert manager.conversation_file == Path(temp_storage) / "conversation.json"

    def test_add_message_success(self, conversation_manager):
        """Test successfully adding a message."""
        success = conversation_manager.add_message(
            role="user", content="Hello", message_type="chat"
        )

        assert success is True

        # Verify message was stored
        history = conversation_manager.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    def test_add_multiple_messages(self, conversation_manager):
        """Test adding multiple messages."""
        conversation_manager.add_message("user", "Hello")
        conversation_manager.add_message("assistant", "Hi there!")
        conversation_manager.add_message("user", "How are you?")

        history = conversation_manager.get_conversation_history()
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"

    def test_truncate_conversation_history(self, temp_storage):
        """Test conversation history truncation."""
        with patch("app.core.conversation_manager.config") as mock_config:
            mock_config.storage_path = temp_storage
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 3

            manager = ConversationManager(temp_storage)

            # Add more messages than the limit
            for i in range(5):
                manager.add_message("user", f"Message {i}")

            history = manager.get_conversation_history()
            assert len(history) == 3
            # Should keep the most recent messages
            assert history[0]["content"] == "Message 2"
            assert history[1]["content"] == "Message 3"
            assert history[2]["content"] == "Message 4"

    def test_clear_conversation_history(self, conversation_manager):
        """Test clearing conversation history."""
        # Add some messages
        conversation_manager.add_message("user", "Hello")
        conversation_manager.add_message("assistant", "Hi!")

        assert len(conversation_manager.get_conversation_history()) == 2

        # Clear history
        success = conversation_manager.clear_conversation_history()
        assert success is True

        # Verify history is cleared
        history = conversation_manager.get_conversation_history()
        assert len(history) == 0

    def test_get_conversation_stats(self, conversation_manager):
        """Test getting conversation statistics."""
        # Add various types of messages
        conversation_manager.add_message("user", "Hello", "chat")
        conversation_manager.add_message("assistant", "Hi!", "chat")
        conversation_manager.add_message(
            "assistant", "Alert message", "alert", alert_id="alert_123"
        )

        stats = conversation_manager.get_conversation_stats()

        assert stats["message_count"] == 3
        assert stats["chat_messages"] == 2
        assert stats["alert_messages"] == 1
        assert "oldest_message" in stats
        assert "newest_message" in stats

    def test_no_authorized_user_id(self, temp_storage):
        """Test behavior when no authorized user ID is configured."""
        with patch("app.core.conversation_manager.config") as mock_config:
            mock_config.storage_path = temp_storage
            mock_config.authorized_user_id = None

            manager = ConversationManager(temp_storage)

            # Should return empty results without errors
            assert manager.get_conversation_history() == []
            assert manager.add_message("user", "test") is False
            assert manager.clear_conversation_history() is False

    def test_file_error_handling(self, conversation_manager):
        """Test handling of file I/O errors."""
        # Test with corrupted JSON file
        conversation_file = conversation_manager.conversation_file

        # Write invalid JSON
        with open(conversation_file, "w") as f:
            f.write("invalid json {")

        # Should handle gracefully and return empty history
        history = conversation_manager.get_conversation_history()
        assert history == []

        # Should still be able to add new messages (overwrites corrupted file)
        success = conversation_manager.add_message("user", "test")
        assert success is True

    def test_max_messages_parameter(self, conversation_manager):
        """Test the max_messages parameter in get_conversation_history."""
        # Add several messages
        for i in range(5):
            conversation_manager.add_message("user", f"Message {i}")

        # Get limited history
        history = conversation_manager.get_conversation_history(max_messages=3)
        assert len(history) == 3

        # Should return the most recent messages
        assert history[0]["content"] == "Message 2"
        assert history[1]["content"] == "Message 3"
        assert history[2]["content"] == "Message 4"

    @patch("app.core.conversation_manager.fcntl.flock")
    def test_file_locking(self, mock_flock, conversation_manager):
        """Test that file locking is used correctly."""
        conversation_manager.add_message("user", "test")

        # Verify flock was called for both reading and writing
        assert mock_flock.called
        assert mock_flock.call_count >= 2  # At least one read and one write


class TestConversationManagerIntegration:
    """Integration tests for the conversation manager."""

    def test_conversation_manager_singleton(self, tmp_path):
        """Test that get_conversation_manager returns a singleton."""
        from app.core.conversation_manager import get_conversation_manager

        # Patch the storage path to use a temporary directory
        with patch("app.core.conversation_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            manager1 = get_conversation_manager()
            manager2 = get_conversation_manager()

            assert manager1 is manager2
