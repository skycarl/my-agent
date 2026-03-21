"""
Workout agent for fetching and managing run data from Strava.

This agent fetches run data, formats it as markdown, supports
adding subjective notes, and returns workout summaries on demand.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.workout.workout_service import (
    fetch_latest_workout as svc_fetch_latest_workout,
    fetch_workout_by_date as svc_fetch_workout_by_date,
    add_notes as svc_add_notes,
    get_workout_summary as svc_get_workout_summary,
)
from app.core.settings import config, get_model_settings_for_agent


@function_tool
async def get_latest_workout() -> str:
    """Fetch the most recent run from Strava and save it as a markdown file."""
    return await svc_fetch_latest_workout()


@function_tool
async def get_workout_by_date(date: str) -> str:
    """
    Fetch a run from Strava for a specific date and save it as a markdown file.

    Args:
        date: The date to look up. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day' (e.g., 'March 19').
    """
    return await svc_fetch_workout_by_date(date)


@function_tool
async def add_workout_notes(date: str, notes: str) -> str:
    """
    Add subjective notes to an existing workout file (nutrition, how you felt, etc).

    Args:
        date: The date of the workout. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day'.
        notes: Free-text notes to add. Each line becomes a bullet point.
    """
    return svc_add_notes(date, notes)


@function_tool
async def get_workout_summary(date: str) -> str:
    """
    Get the full markdown content of a workout file for a given date.

    Args:
        date: The date of the workout. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day'.
    """
    return svc_get_workout_summary(date)


def create_workout_agent(model: str = None) -> Agent:
    """
    Create a Workout agent with Strava integration tools.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Workout agent
    """
    agent_model = model or config.default_model
    agent_model_settings = get_model_settings_for_agent("workout")

    workout = Agent(
        name="Workout",
        handoff_description="Handles workout tracking: fetching run data from Strava, adding subjective notes, and retrieving workout summaries.",
        **({"model_settings": agent_model_settings} if agent_model_settings else {}),
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are a workout tracking assistant. You help the user fetch run data from Strava, add notes about how they felt, and retrieve workout summaries.

Tool usage:
- Use `get_latest_workout` when the user says "grab my run", "get my latest run", or similar.
- Use `get_workout_by_date` when a specific date is mentioned (e.g., "get my run from Tuesday").
- Use `add_workout_notes` when the user wants to record how they felt, nutrition, or other subjective notes.
- Use `get_workout_summary` when the user wants the full markdown to copy/paste.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[
            get_latest_workout,
            get_workout_by_date,
            add_workout_notes,
            get_workout_summary,
        ],
        model=agent_model,
    )

    logger.debug(f"Workout agent created with model '{agent_model}'")
    return workout
