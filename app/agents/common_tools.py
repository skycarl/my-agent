"""Shared `@function_tool`s used by more than one agent."""

from agents import function_tool

from app.core.timezone_utils import now_local


@function_tool
async def get_current_date() -> str:
    """Get the current date and time so the agent can resolve relative references like 'today', 'tomorrow', 'this week', or the current month/year."""
    now = now_local()
    return str(
        {
            "current_date": now.strftime("%Y-%m-%d"),
            "current_day": now.strftime("%A"),
            "current_time": now.strftime("%H:%M"),
            "current_month_year": now.strftime("%B %Y"),
            "timezone": "Pacific Time",
        }
    )
