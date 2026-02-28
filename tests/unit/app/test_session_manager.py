"""
Tests for the session manager.
"""

import pytest
from unittest.mock import patch
from agents import SQLiteSession


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

            assert isinstance(session, SQLiteSession)

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
