"""
Commute assistant agent for handling commuting-related queries.

This agent specializes in commute information and uses direct tool calls
to provide transportation-related assistance.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.commute.commute_service import (
    get_monorail_hours as svc_get_monorail_hours,
    get_recent_alerts as svc_get_recent_alerts,
)
from app.agents.commute.preferences_service import (
    read_preferences_file as svc_read_preferences_file,
    write_preferences_file as svc_write_preferences_file,
    get_commute_overrides as svc_get_commute_overrides,
    add_commute_override as svc_add_commute_override,
    remove_commute_override as svc_remove_commute_override,
)
from app.core.settings import config, get_model_settings_for_agent
from app.core.timezone_utils import now_local


@function_tool
async def get_monorail_hours() -> str:
    """Get the current operating hours for the Seattle Monorail."""
    result = svc_get_monorail_hours()
    return str(result.model_dump())


@function_tool
async def get_current_date() -> str:
    """Get the current date and time information to understand context for transportation schedules."""
    now = now_local()
    return str(
        {
            "current_date": now.strftime("%Y-%m-%d"),
            "current_day": now.strftime("%A"),
            "current_time": now.strftime("%H:%M"),
            "timezone": "Pacific Time",
        }
    )


@function_tool
async def get_recent_alerts(limit: int = 5) -> str:
    """Get recent commute alerts that were processed by the system."""
    result = svc_get_recent_alerts(limit)
    return str(result.model_dump())


@function_tool
async def read_commute_preferences() -> str:
    """Read the user's commute preferences file (schedule, routes, etc.)."""
    return svc_read_preferences_file()


@function_tool
async def write_commute_preferences(content: str) -> str:
    """Overwrite the commute preferences file with updated content. Always read first before writing."""
    return svc_write_preferences_file(content)


@function_tool
async def get_commute_overrides_tool() -> str:
    """Get active ad hoc commute overrides (e.g., working from home on a normally in-office day)."""
    overrides = svc_get_commute_overrides()
    return str(overrides)


@function_tool
async def add_commute_override_tool(date: str, override_type: str, note: str) -> str:
    """Add an ad hoc commute override for a specific date.

    Args:
        date: The date this override applies to (YYYY-MM-DD).
        override_type: Either "commute_day" (going in on a normally remote day) or "remote_day" (staying home on a normally in-office day).
        note: Human-readable note about why (e.g., "dentist appointment").
    """
    result = svc_add_commute_override(date=date, override_type=override_type, note=note)
    return str(result)


@function_tool
async def remove_commute_override_tool(override_id: str) -> str:
    """Remove an ad hoc commute override by its ID."""
    removed = svc_remove_commute_override(override_id)
    return f"Override {'removed' if removed else 'not found'}."


def create_commute_agent(model: str = None) -> Agent:
    """
    Create a Commute Assistant agent with direct tool calls.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Commute Assistant agent
    """
    agent_model = model or config.default_model
    agent_model_settings = get_model_settings_for_agent("commute")

    commute = Agent(
        name="Commute Assistant",
        handoff_description="Handles commute and transportation queries: Seattle Monorail hours, schedules, recent transit alerts, and commute preferences/overrides.",
        **({"model_settings": agent_model_settings} if agent_model_settings else {}),
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are the Commute Assistant - a specialized agent for handling transportation and commute-related queries.

You help the user with:
- Seattle Monorail operating hours and schedules
- Looking up recent transit alerts
- Managing commute preferences (regular schedule, route preferences)
- Managing ad hoc commute overrides (e.g., "I'm going into the city tomorrow", "working from home Thursday")

## Commute Preferences
- Use `read_commute_preferences` to view the current schedule and route preferences.
- Use `write_commute_preferences` to update the preferences file. **Always read before writing** so you preserve existing content. Only remove content the user explicitly asks to remove.
- The preferences file is human-readable markdown with sections for Regular Schedule and Route Preferences.

## Commute Overrides
- Use `get_commute_overrides_tool` to see active ad hoc overrides.
- Use `add_commute_override_tool` to add a one-off schedule change (e.g., "commute_day" for going in on a remote day, "remote_day" for staying home on an office day).
- Use `remove_commute_override_tool` to delete an override by ID.
- Overrides automatically expire after the date they apply to.

Guidelines:
- Always consider what day it is today (use get_current_date when relevant).
- Use your tools to answer the user's query.
- Do not make up information that is not grounded in a tool response. If you cannot answer, say so.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[
            get_monorail_hours,
            get_current_date,
            get_recent_alerts,
            read_commute_preferences,
            write_commute_preferences,
            get_commute_overrides_tool,
            add_commute_override_tool,
            remove_commute_override_tool,
        ],
        model=agent_model,
    )

    logger.debug(f"Commute agent created with model '{agent_model}'")
    return commute
