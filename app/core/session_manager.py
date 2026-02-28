"""
Session manager using the OpenAI Agents SDK SQLiteSession.

Provides a singleton SQLiteSession that automatically persists
the full conversation state (including tool calls, tool results,
and handoff context) through Runner.run().
"""

from pathlib import Path

from agents import SQLiteSession, SessionSettings
from loguru import logger

from app.core.settings import config

_session: SQLiteSession | None = None


def get_session() -> SQLiteSession:
    """Get the global SQLiteSession instance, creating it if needed."""
    global _session
    if _session is None:
        db_path = Path(config.storage_path) / "conversation.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        session_id = str(config.authorized_user_id)
        session_settings = SessionSettings(limit=config.max_conversation_history)

        _session = SQLiteSession(
            session_id=session_id,
            db_path=db_path,
            session_settings=session_settings,
        )
        logger.debug(
            f"Created SQLiteSession (session_id={session_id}, db_path={db_path})"
        )
    return _session


def reset_session() -> None:
    """Close and clear the singleton session (for shutdown and testing)."""
    global _session
    if _session is not None:
        _session.close()
        logger.debug("SQLiteSession closed")
        _session = None
