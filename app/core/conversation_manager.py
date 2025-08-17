"""
Persistent conversation history manager.

This module provides centralized conversation history management using
disk-based JSON storage. It supports a single user conversation history
and ensures thread-safe file operations.
"""

import json
import fcntl
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger
from pydantic import BaseModel, Field
from app.core.settings import config
from app.core.timezone_utils import now_local_isoformat


class ConversationMessage(BaseModel):
    """Represents a single message in conversation history."""

    role: str = Field(description="Message role: user, assistant, or system")
    content: str = Field(description="Message content")
    message_type: str = Field(
        default="chat", description="Type of message: chat or alert"
    )
    timestamp: str = Field(
        default_factory=now_local_isoformat,
        description="ISO timestamp when message was created",
    )
    message_id: Optional[str] = Field(
        default=None, description="Optional message ID for tracking"
    )
    alert_id: Optional[str] = Field(
        default=None, description="Optional alert ID for alert messages"
    )


class ConversationManager:
    """Manages persistent conversation history for the application."""

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize conversation manager.

        Args:
            storage_path: Optional custom storage path, defaults to config
        """
        self.storage_dir = Path(storage_path or config.storage_path)
        self.storage_dir.mkdir(exist_ok=True)
        self.conversation_file = self.storage_dir / "conversation.json"

        # Since we only support single user, use the authorized user ID
        self.user_id = config.authorized_user_id

        if not self.user_id:
            logger.warning(
                "No authorized user ID configured for conversation management"
            )

    def _read_conversation_file(self) -> Dict:
        """
        Read conversation file with file locking.

        Returns:
            Dict containing conversation data
        """
        if not self.conversation_file.exists():
            return {}

        try:
            with open(self.conversation_file, "r", encoding="utf-8") as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Error reading conversation file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error reading conversation file: {e}")
            return {}

    def _write_conversation_file(self, data: Dict) -> None:
        """
        Write conversation file with file locking.

        Args:
            data: Dict containing conversation data to write
        """
        try:
            # Write to temporary file first, then move for atomic operation
            temp_file = self.conversation_file.with_suffix(".tmp")

            with open(temp_file, "w", encoding="utf-8") as f:
                # Acquire exclusive lock for writing
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Atomic move
            temp_file.replace(self.conversation_file)

        except Exception as e:
            logger.error(f"Error writing conversation file: {e}")
            # Clean up temp file if it exists
            if temp_file.exists():
                temp_file.unlink()
            raise

    def get_conversation_history(
        self, max_messages: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation history for the authorized user.

        Args:
            max_messages: Optional limit on number of recent messages to return

        Returns:
            List of message dictionaries suitable for AI agents
        """
        if not self.user_id:
            logger.warning("Cannot get conversation history: no authorized user ID")
            return []

        try:
            data = self._read_conversation_file()
            user_key = str(self.user_id)

            if user_key not in data:
                return []

            messages = data[user_key]

            # Apply message limit if specified
            if max_messages and len(messages) > max_messages:
                messages = messages[-max_messages:]

            # Convert to format expected by AI agents (role, content only)
            return [
                {"role": msg["role"], "content": msg["content"]} for msg in messages
            ]

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

    def add_message(
        self,
        role: str,
        content: str,
        message_type: str = "chat",
        message_id: Optional[str] = None,
        alert_id: Optional[str] = None,
    ) -> bool:
        """
        Add a message to conversation history.

        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
            message_type: Type of message ("chat", "alert")
            message_id: Optional message ID for tracking
            alert_id: Optional alert ID for alert messages

        Returns:
            True if successful, False otherwise
        """
        if not self.user_id:
            logger.warning("Cannot add message: no authorized user ID")
            return False

        try:
            # Create message object
            message = ConversationMessage(
                role=role,
                content=content,
                message_type=message_type,
                message_id=message_id,
                alert_id=alert_id,
            )

            # Read current data
            data = self._read_conversation_file()
            user_key = str(self.user_id)

            # Initialize user's conversation if needed
            if user_key not in data:
                data[user_key] = []

            # Add message
            data[user_key].append(message.model_dump())

            # Truncate if too long
            max_history = config.max_conversation_history
            if len(data[user_key]) > max_history:
                data[user_key] = data[user_key][-max_history:]
                logger.debug(
                    f"Truncated conversation history to {max_history} messages"
                )

            # Write back to file
            self._write_conversation_file(data)

            logger.debug(
                f"Added {role} message to conversation history: {content[:100]}..."
            )
            return True

        except Exception as e:
            logger.error(f"Error adding message to conversation history: {e}")
            return False

    def clear_conversation_history(self) -> bool:
        """
        Clear conversation history for the authorized user.

        Returns:
            True if successful, False otherwise
        """
        if not self.user_id:
            logger.warning("Cannot clear conversation history: no authorized user ID")
            return False

        try:
            data = self._read_conversation_file()
            user_key = str(self.user_id)

            if user_key in data:
                del data[user_key]
                self._write_conversation_file(data)
                logger.info(f"Cleared conversation history for user {self.user_id}")

            return True

        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            return False

    def get_conversation_stats(self) -> Dict:
        """
        Get statistics about conversation history.

        Returns:
            Dict containing stats like message count, types, etc.
        """
        if not self.user_id:
            return {"error": "No authorized user ID"}

        try:
            data = self._read_conversation_file()
            user_key = str(self.user_id)

            if user_key not in data:
                return {"message_count": 0, "chat_messages": 0, "alert_messages": 0}

            messages = data[user_key]
            chat_count = sum(
                1 for msg in messages if msg.get("message_type", "chat") == "chat"
            )
            alert_count = sum(
                1 for msg in messages if msg.get("message_type", "chat") == "alert"
            )

            return {
                "message_count": len(messages),
                "chat_messages": chat_count,
                "alert_messages": alert_count,
                "oldest_message": messages[0]["timestamp"] if messages else None,
                "newest_message": messages[-1]["timestamp"] if messages else None,
            }

        except Exception as e:
            logger.error(f"Error getting conversation stats: {e}")
            return {"error": str(e)}


# Global conversation manager instance
_conversation_manager = None


def get_conversation_manager() -> ConversationManager:
    """Get the global conversation manager instance."""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
