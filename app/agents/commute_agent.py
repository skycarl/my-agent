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
from app.core.settings import config
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


def create_commute_agent(model: str = None) -> Agent:
    """
    Create a Commute Assistant agent with direct tool calls.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Commute Assistant agent
    """
    agent_model = model or config.default_model

    commute = Agent(
        name="Commute Assistant",
        handoff_description="Handles commute and transportation queries: Seattle Monorail hours, schedules, and recent transit alerts.",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are the Commute Assistant - a specialized agent for handling transportation and commute-related queries.

You help the user with:
- Seattle Monorail operating hours and schedules
- Looking up recent transit alerts

Guidelines:
- Always consider what day it is today (use get_current_date when relevant).
- Use your tools to answer the user's query.
- Do not make up information that is not grounded in a tool response. If you cannot answer, say so.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[get_monorail_hours, get_current_date, get_recent_alerts],
        model=agent_model,
    )

    logger.debug(f"Commute agent created with model '{agent_model}'")
    return commute
