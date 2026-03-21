"""
Workout agent for fetching and managing workout data from Strava.

This agent fetches activity data (runs, rides, strength), formats it
as structured markdown, supports adding subjective notes and other
manual sections, and returns workout summaries on demand.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.workout.workout_service import (
    fetch_latest_workout as svc_fetch_latest_workout,
    fetch_workout_by_date as svc_fetch_workout_by_date,
    update_section as svc_update_section,
    get_workout_summary as svc_get_workout_summary,
)
from app.core.settings import config, get_model_settings_for_agent


@function_tool
async def get_latest_workout() -> str:
    """Fetch the most recent activity from Strava and save it as a structured markdown file with all objective data (summary, splits, laps, HR zones, best efforts)."""
    return await svc_fetch_latest_workout()


@function_tool
async def get_workout_by_date(date: str) -> str:
    """
    Fetch an activity from Strava for a specific date and save it as a structured markdown file.

    Args:
        date: The date to look up. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day' (e.g., 'March 19').
    """
    return await svc_fetch_workout_by_date(date)


@function_tool
async def update_workout_section(date: str, section: str, content: str) -> str:
    """
    Update or add a section in an existing workout markdown file. Use this for subjective notes, fueling, COROS extras, and context.

    Args:
        date: The date of the workout. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day'.
        section: The section name to update. One of: 'Subjective Notes', 'Fueling', 'COROS Extras', 'Context'.
        content: The full content for that section in markdown format.
    """
    return svc_update_section(date, section, content)


@function_tool
async def get_workout_summary(date: str) -> str:
    """
    Get the full markdown content of a workout file for a given date. Returns the complete file for copy/paste.

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
        handoff_description="Handles workout tracking: fetching activity data from Strava (runs, rides, strength), adding subjective notes/fueling/context, and retrieving workout summaries.",
        **({"model_settings": agent_model_settings} if agent_model_settings else {}),
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are a workout tracking assistant. You help the user fetch activity data from Strava, add subjective notes and other manual sections, and retrieve workout summaries.

Tool usage:
- Use `get_latest_workout` ONLY when the user explicitly wants to fetch/import a NEW workout from Strava (e.g., "grab my run", "get my latest workout", "import my ride").
- Use `get_workout_by_date` ONLY when the user wants to fetch/import a workout from Strava for a specific date.
- Use `get_workout_summary` when the user wants to SEE or RETRIEVE an existing workout (e.g., "send me today's workout", "show me my workout", "give me the markdown"). NEVER re-fetch from Strava when the user just wants to see what's already saved.
- Use `update_workout_section` when the user wants to add subjective notes, fueling data, COROS extras, or context. Format the content as markdown matching the template structure:
  - For "Subjective Notes": include **Pre-run:**, **During:**, **Post-run:** blockquote sections.
  - For "Fueling": use a markdown table with columns Timing, Item, Carbs, Caffeine, Sodium, Water.
  - For "COROS Extras": use a markdown table with Metric and Value columns.
  - For "Context": use a blockquote with the context text.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[
            get_latest_workout,
            get_workout_by_date,
            update_workout_section,
            get_workout_summary,
        ],
        model=agent_model,
    )

    logger.debug(f"Workout agent created with model '{agent_model}'")
    return workout
