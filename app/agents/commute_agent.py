"""
Commute assistant agent for handling commuting-related queries.

This agent specializes in commute information and uses direct tool calls
to provide transportation-related assistance.
"""

from agents import Agent, function_tool
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
        instructions="""You are the Commute Assistant - a specialized agent for handling transportation and commute-related tasks. You help the user with:

    1. Seattle Monorail operating hours and schedules
    2. Processing transportation alerts and determining if they are relevant to the user

    You have access to tools that provide:
    - get_monorail_hours: Get current Seattle Monorail operating hours for each day
    - get_current_date: Get current date and time information for context
    - get_recent_alerts: Look up recent commute alerts that were previously processed by the system

     You may be invoked through two paths:
     1) The user asking you a question about commuting or transportation by sending you a message. These will be in natural language.
     2) An automated alert from a transportation authority or service provider to process in the format: "Process this alert: {JSON data}"

    You must respond with a JSON object wrapped in XML tags containing exactly these three keys:
    <json>
    {
      "rationale": "string",
      "notify_user": boolean,
      "message_content": "string"
    }
    </json>

    When processing user queries:
    - Be helpful and provide clear, actionable transportation information.
    - Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
    - Always consider what day it is today (use your get_current_date tool when relevant).
    - Use your tools to answer the user's query.
    - Do not make up information that is not grounded in a tool response. If you cannot answer the user's query because you don't have enough information, say so.
    - Always use `"notify_user": True` because you were asked a direct question by the user.
    - Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.

    When you receive "Process this alert:" followed by JSON data:
    - You must decide if the alert is relevant to the user. If it is, then you must set notify_user to true. If it is not relevant, then you must set notify_user to false.
    - Alert types that are relevant to the user:
        * Delays, service disruptions, or schedule changes
        * Emergency transportation alerts
        * Schedule changes that affect daily commuting
        * Weather-related transportation impacts
    - Alerts to ignore:
        * Elevator outages
        * Vending machine outages
        * Other non-commute related alerts
    - If the alert contains any hyperlinks, do not relay them to the user.

    Examples:

    For relevant alerts:
    <json>
    {
        "rationale": "This alert is about a track blockage, which affects commuting schedules.",
        "notify_user": true,
        "message_content": "Track blockage affecting 2 Line trains. Trains running every 20-25 minutes until further notice. Expect longer wait times."
    }
    </json>

    For non-relevant alerts:
    <json>
    {
        "rationale": "This alert is about elevator maintenance, which doesn't affect commuting schedules.",
        "notify_user": false,
        "message_content": ""
    }
    </json>

    General guidelines:
    - Always use "rationale": "string" to explain why you are notifying the user, or are not notifying the user.
    - Use your get_current_date tool to check if the alert is timely
    - Format a clear, concise notification message
    - Include relevant details like affected routes, estimated delays, and alternative options
    - Only use information available in the alert body or from your tools; do not make up information.
    """,
        tools=[get_monorail_hours, get_current_date, get_recent_alerts],
        model=agent_model,
    )

    logger.debug(f"Commute agent created with model '{agent_model}'")
    return commute
