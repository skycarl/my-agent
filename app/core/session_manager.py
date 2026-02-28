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


_session: SafeSQLiteSession | None = None


def get_session() -> SafeSQLiteSession:
    """Get the global SafeSQLiteSession instance, creating it if needed."""
    global _session
    if _session is None:
        db_path = Path(config.storage_path) / "conversation.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        session_id = str(config.authorized_user_id)
        session_settings = SessionSettings(limit=config.max_conversation_history)

        _session = SafeSQLiteSession(
            session_id=session_id,
            db_path=db_path,
            session_settings=session_settings,
        )
        logger.debug(
            f"Created SafeSQLiteSession (session_id={session_id}, db_path={db_path})"
        )
    return _session


def reset_session() -> None:
    """Close and clear the singleton session (for shutdown and testing)."""
    global _session
    if _session is not None:
        _session.close()
        logger.debug("SafeSQLiteSession closed")
        _session = None
