"""
Session manager using the OpenAI Agents SDK SQLiteSession.

Provides a singleton SafeSQLiteSession that automatically persists
the full conversation state (including tool calls, tool results,
and handoff context) through Runner.run().

The SafeSQLiteSession subclass strips orphaned function_call_output
items after truncation so the API never receives dangling call_ids.
"""

from pathlib import Path

from agents import SQLiteSession, SessionSettings
from loguru import logger

from app.core.settings import config


class SafeSQLiteSession(SQLiteSession):
    """SQLiteSession that sanitizes truncated history.

    When the session limit truncates older items, a function_call may be
    dropped while its function_call_output survives.  The OpenAI API rejects
    conversations with orphaned outputs.  This subclass filters them out.
    """

    async def get_items(self, limit=None):
        items = await super().get_items(limit)

        valid_call_ids = {
            item["call_id"] for item in items if item.get("type") == "function_call"
        }

        sanitized = [
            item
            for item in items
            if item.get("type") != "function_call_output"
            or item.get("call_id") in valid_call_ids
        ]

        dropped = len(items) - len(sanitized)
        if dropped:
            logger.debug(
                f"Dropped {dropped} orphaned function_call_output(s) from session history"
            )

        return sanitized


# One SafeSQLiteSession per conversation_id (Telegram chat_id), all sharing the
# same SQLite file but with distinct session_ids.
_sessions: dict[str, SafeSQLiteSession] = {}


def get_session(conversation_id: str) -> SafeSQLiteSession:
    """Get the SafeSQLiteSession for a conversation, creating it if needed.

    Args:
        conversation_id: The conversation key (Telegram chat_id as a string).
    """
    session_id = str(conversation_id)
    session = _sessions.get(session_id)
    if session is None:
        db_path = Path(config.storage_path) / "conversation.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        session_settings = SessionSettings(limit=config.max_conversation_history)

        session = SafeSQLiteSession(
            session_id=session_id,
            db_path=db_path,
            session_settings=session_settings,
        )
        _sessions[session_id] = session
        logger.debug(
            f"Created SafeSQLiteSession (session_id={session_id}, db_path={db_path})"
        )
    return session


async def clear_session(conversation_id: str) -> None:
    """Clear the stored history for a single conversation."""
    session = get_session(conversation_id)
    await session.clear_session()


def reset_session() -> None:
    """Close and clear all cached sessions (for shutdown and testing)."""
    global _sessions
    for session in _sessions.values():
        session.close()
    if _sessions:
        logger.debug(f"Closed {len(_sessions)} SafeSQLiteSession(s)")
    _sessions = {}
