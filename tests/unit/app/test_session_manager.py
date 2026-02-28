"""
Tests for the session manager.
"""

import pytest
from unittest.mock import patch
from agents import SQLiteSession

from app.core.session_manager import SafeSQLiteSession


class TestSessionManager:
    """Test the session manager singleton."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        """Reset the global singleton before and after each test."""
        import app.core.session_manager as sm

        sm._session = None
        yield
        if sm._session is not None:
            sm._session.close()
            sm._session = None

    def test_get_session_creates_instance(self, tmp_path):
        """Verify get_session returns a SQLiteSession."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            session = get_session()

            assert isinstance(session, SafeSQLiteSession)
            assert isinstance(session, SQLiteSession)  # subclass of SQLiteSession

    def test_get_session_returns_singleton(self, tmp_path):
        """Same instance returned on repeated calls."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            session1 = get_session()
            session2 = get_session()

            assert session1 is session2

    def test_reset_session_clears_instance(self, tmp_path):
        """reset_session clears and closes the singleton."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session, reset_session
            import app.core.session_manager as sm

            get_session()
            assert sm._session is not None

            reset_session()
            assert sm._session is None

    @pytest.mark.asyncio
    async def test_session_clear(self, tmp_path):
        """Verify clear_session works without error."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            session = get_session()

            # Add an item then clear
            await session.add_items([{"role": "user", "content": "hello"}])
            items_before = await session.get_items()
            assert len(items_before) > 0

            await session.clear_session()

            items_after = await session.get_items()
            assert len(items_after) == 0

    @pytest.mark.asyncio
    async def test_session_limit(self, tmp_path):
        """Verify SessionSettings limit is respected."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 3

            from app.core.session_manager import get_session

            session = get_session()

            # Add more items than the limit
            for i in range(5):
                await session.add_items([{"role": "user", "content": f"message {i}"}])

            items = await session.get_items()
            assert len(items) == 3

    @pytest.mark.asyncio
    async def test_orphaned_function_call_outputs_stripped(self, tmp_path):
        """Verify that orphaned function_call_output items are dropped after truncation."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 3

            from app.core.session_manager import get_session

            session = get_session()

            # Simulate a conversation: function_call + output, then a user message.
            # With limit=3, the function_call will be truncated but its output survives.
            await session.add_items(
                [
                    {
                        "type": "function_call",
                        "call_id": "call_old",
                        "name": "foo",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_old",
                        "output": "bar",
                    },
                    {"type": "message", "role": "user", "content": "msg1"},
                    {
                        "type": "function_call",
                        "call_id": "call_new",
                        "name": "baz",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_new",
                        "output": "qux",
                    },
                ]
            )

            items = await session.get_items()

            # The oldest items are truncated to limit=3, leaving the last 3 rows:
            # msg1, function_call(call_new), function_call_output(call_new)
            # The orphaned function_call_output(call_old) should NOT be present.
            orphaned = [
                item
                for item in items
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "call_old"
            ]
            assert len(orphaned) == 0

            # The valid pair should still be intact
            valid_outputs = [
                item
                for item in items
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "call_new"
            ]
            assert len(valid_outputs) == 1

    def test_db_file_created(self, tmp_path):
        """Verify the SQLite database file is created in the storage path."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.authorized_user_id = 12345
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            get_session()

            db_file = tmp_path / "conversation.db"
            assert db_file.exists()
