"""
Per-request conversation context.

Holds the conversation_id (Telegram chat_id, as a string) of the request
currently being processed, so that tools invoked deep inside an agent run —
notably the scheduler's ``schedule_task`` — can capture which conversation
spawned them without threading the value through every agent and handoff.

The value is set in the ``/agent_response`` endpoint before ``Runner.run`` and
read inside the tool. contextvars propagate through the awaited tool calls, so
the value set before the run is visible to tools executed during it.
"""

from contextvars import ContextVar
from typing import Optional

_current_conversation_id: ContextVar[Optional[str]] = ContextVar(
    "current_conversation_id", default=None
)


def set_conversation_id(conversation_id: Optional[str]) -> None:
    """Set the conversation_id for the current async context."""
    _current_conversation_id.set(conversation_id)


def get_conversation_id() -> Optional[str]:
    """Get the conversation_id for the current async context, or None."""
    return _current_conversation_id.get()
