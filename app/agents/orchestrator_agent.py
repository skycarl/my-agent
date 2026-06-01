"""
Orchestrator agent for routing requests to specialized agents.

This agent acts as the main entry point and decides which specialized
agent should handle each request through agent handoffs.
"""

from agents import Agent, WebSearchTool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger
from app.core.settings import config
from .gardener_agent import create_gardener_agent
from .commute_agent import create_commute_agent
from .scheduler_agent import create_scheduler_agent
from .workout_agent import create_workout_agent
from .travel_alerts_agent import create_travel_alerts_agent
from .private_loader import load_private_agents


def create_orchestrator_agent(model: str = None) -> Agent:
    """
    Create an Orchestrator agent with handoffs to specialized agents.

    Args:
        model: The OpenAI model to use for this agent and its handoffs

    Returns:
        Configured Orchestrator agent
    """
    # Use provided model or fall back to default
    agent_model = model or config.default_model

    # Create specialized agents with the same model
    gardener_agent = create_gardener_agent(agent_model)
    commute_agent = create_commute_agent(agent_model)
    scheduler_agent = create_scheduler_agent(agent_model)
    workout_agent = create_workout_agent(agent_model)
    travel_alerts_agent = create_travel_alerts_agent(agent_model)

    handoffs = [
        gardener_agent,
        commute_agent,
        scheduler_agent,
        workout_agent,
        travel_alerts_agent,
    ]
    handoffs += load_private_agents(agent_model)

    orchestrator = Agent(
        name="Orchestrator",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are an orchestrator that routes user requests to specialized agents.

Routing guidelines:
- Garden, plant, harvest, or farming topics → Gardener
- Commute, transportation, or transit topics → Commute Assistant
- "schedule", "remind", "repeat", cron patterns, or specific date/time → Scheduler
- Workout, running, Strava, exercise, or training topics → Workout
- Travel alerts or local news for a place (e.g. "travel alerts for Rome", "anything I should know before going to London?") → Travel Alerts
- Otherwise, if another available agent's description matches the request, hand off to it
- Generic questions needing up-to-date or external info (current events, weather, general facts, looking something up online) → use the web_search tool and answer directly
- Other general questions → Handle directly

When unsure, lean towards the most relevant specialized agent.

If the user sends an image, analyze it and route based on its content (e.g., a schedule or date list → Scheduler).

Scheduled task messages: If a message looks like a reminder rather than a genuine request (e.g., "Time to water the garden"), deliver it directly instead of routing to the Scheduler.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        handoffs=handoffs,
        tools=[WebSearchTool()],
        model=agent_model,
    )

    logger.debug(
        f"Orchestrator agent created with model '{agent_model}' and handoffs to Gardener, Commute Assistant, Scheduler, Workout, and Travel Alerts agents"
    )
    return orchestrator
