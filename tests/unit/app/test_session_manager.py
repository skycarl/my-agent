"""
Tests for the session manager.
"""

import pytest
from unittest.mock import patch
from agents import SQLiteSession

from app.core.session_manager import SafeSQLiteSession

CONV = "12345"


class TestSessionManager:
    """Test the per-conversation session manager."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        """Reset the session cache before and after each test."""
        import app.core.session_manager as sm

        sm.reset_session()
        yield
        sm.reset_session()

    def test_get_session_creates_instance(self, tmp_path):
        """Verify get_session returns a SQLiteSession."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            session = get_session(CONV)

            assert isinstance(session, SafeSQLiteSession)
            assert isinstance(session, SQLiteSession)  # subclass of SQLiteSession

    def test_get_session_caches_per_conversation(self, tmp_path):
        """Same instance returned for the same conversation; distinct for others."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            session1 = get_session(CONV)
            session2 = get_session(CONV)
            other = get_session("99999")

            assert session1 is session2
            assert other is not session1

    def test_reset_session_clears_instances(self, tmp_path):
        """reset_session closes and clears all cached sessions."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session, reset_session
            import app.core.session_manager as sm

            get_session(CONV)
            assert sm._sessions

            reset_session()
            assert sm._sessions == {}

    @pytest.mark.asyncio
    async def test_clear_session(self, tmp_path):
        """Verify clear_session empties a single conversation's history."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session, clear_session

            session = get_session(CONV)

            await session.add_items([{"role": "user", "content": "hello"}])
            assert len(await session.get_items()) > 0

            await clear_session(CONV)

            assert len(await session.get_items()) == 0

    @pytest.mark.asyncio
    async def test_sessions_are_isolated(self, tmp_path):
        """Items added to one conversation do not appear in another."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            a = get_session("conv_a")
            b = get_session("conv_b")

            await a.add_items([{"role": "user", "content": "only in a"}])

            assert len(await a.get_items()) == 1
            assert len(await b.get_items()) == 0

    @pytest.mark.asyncio
    async def test_session_limit(self, tmp_path):
        """Verify SessionSettings limit is respected."""
        with patch("app.core.session_manager.config") as mock_config:
            mock_config.storage_path = str(tmp_path)
            mock_config.max_conversation_history = 3

            from app.core.session_manager import get_session

            session = get_session(CONV)

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
            mock_config.max_conversation_history = 3

            from app.core.session_manager import get_session

            session = get_session(CONV)

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
            mock_config.max_conversation_history = 10

            from app.core.session_manager import get_session

            get_session(CONV)

            db_file = tmp_path / "conversation.db"
            assert db_file.exists()
