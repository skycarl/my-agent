"""
Dedicated alert processing agent for transportation alerts.

This agent uses structured output (output_type) to produce an AlertDecision,
eliminating the need for fragile <json> tag parsing.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger
from pydantic import BaseModel

from app.agents.commute.commute_service import (
    get_recent_alerts as svc_get_recent_alerts,
)
from app.core.settings import config
from app.core.timezone_utils import now_local


class AlertDecision(BaseModel):
    rationale: str
    notify_user: bool
    message_content: str


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


def create_alert_processor_agent(model: str = None) -> Agent:
    """
    Create an Alert Processor agent with structured output.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Alert Processor agent with output_type=AlertDecision
    """
    agent_model = model or config.default_model

    alert_processor = Agent(
        name="Alert Processor",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are the Alert Processor - a specialized agent for processing transportation alerts and deciding whether to notify the user.

You receive alerts in the format: "Process this alert: {{JSON data}}"

Your job is to:
1. Analyze the alert content
2. Decide if it is relevant to the user's commute
3. If relevant, format a clear notification message
4. If not relevant, set notify_user to false

**Relevant alerts** (notify_user=true):
- Delays, service disruptions, or schedule changes
- Emergency transportation alerts
- Schedule changes that affect daily commuting
- Weather-related transportation impacts

**Irrelevant alerts** (notify_user=false):
- Elevator outages
- Vending machine outages
- Other non-commute related alerts

**Guidelines:**
- Use get_current_date to check if the alert is timely
- Use get_recent_alerts to check for duplicate or related alerts
- Do not relay hyperlinks to the user
- Format a clear, concise notification message with relevant details (affected routes, estimated delays, alternatives)
- Only use information available in the alert body or from your tools; do not make up information
- Always provide a rationale explaining your decision
""",
        tools=[get_current_date, get_recent_alerts],
        output_type=AlertDecision,
        model=agent_model,
    )

    logger.debug(f"Alert Processor agent created with model '{agent_model}'")
    return alert_processor
