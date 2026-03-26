"""
Logger agent for tracking actions with timestamps and location.

This agent handles action logging (writing to CSV) and querying log history.
Location is automatically fetched from Home Assistant.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.logger.location_service import get_phone_location
from app.agents.logger.logger_service import (
    log_action as svc_log_action,
    query_action_log as svc_query_action_log,
)
from app.core.settings import config, get_model_settings_for_agent


@function_tool
async def log_action(action: str) -> str:
    """
    Log an action with the current timestamp and phone location.

    Args:
        action: Name of the action to log (e.g., "medication", "fed dog")
    """
    latitude, longitude = await get_phone_location()
    result = svc_log_action(action, latitude, longitude)
    return result


@function_tool
async def query_action_log(action: str = "", days: int = 7) -> str:
    """
    Query the action log history.

    Args:
        action: Filter by action name (case-insensitive). Empty string for all actions.
        days: Number of days to look back. Defaults to 7.
    """
    result = svc_query_action_log(action or None, days)
    return result


def create_logger_agent(model: str = None) -> Agent:
    """
    Create a Logger agent for action tracking.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Logger agent
    """
    agent_model = model or config.default_model
    agent_model_settings = get_model_settings_for_agent("logger")

    logger_agent = Agent(
        name="Logger",
        handoff_description="Handles action logging: recording timestamped actions with GPS location and querying log history.",
        **({"model_settings": agent_model_settings} if agent_model_settings else {}),
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are a specialized action logging assistant. You help users log actions and query their action history.

When a user wants to log an action, use the `log_action` tool with the action name. Location is fetched automatically from Home Assistant.

When a user asks about their log history (e.g., "how many times did I take medication this week?"), use `query_action_log` to retrieve and summarize the data.

Be concise and to the point. Confirm each logged action with the timestamp and location if available.
""",
        tools=[log_action, query_action_log],
        model=agent_model,
    )

    logger.debug(f"Logger agent created with model '{agent_model}'")
    return logger_agent
