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
    list_workouts_on_date as svc_list_workouts_on_date,
    update_section as svc_update_section,
    get_workout_summary as svc_get_workout_summary,
)
from app.core.settings import config, get_model_settings_for_agent


@function_tool
async def get_latest_workout() -> str:
    """Fetch the most recent activity from Strava and save it as a structured markdown file with all objective data (summary, splits, laps, HR zones, best efforts)."""
    return await svc_fetch_latest_workout()


@function_tool
async def get_workout_by_date(date: str, activity_type: str | None = None) -> str:
    """
    Fetch an activity from Strava for a specific date and save it as a structured markdown file.

    Args:
        date: The date to look up. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day' (e.g., 'March 19').
        activity_type: Optional filter to pick among multiple activities on the same date, e.g. 'run', 'walk', 'ride', 'weighttraining'. Omit when there is only one activity. If the choice is still ambiguous, the available activities are listed back so you can retry with a more specific filter.
    """
    return await svc_fetch_workout_by_date(date, activity_type)


@function_tool
async def list_workouts_on_date(date: str) -> str:
    """
    List all Strava activities on a specific date without saving anything. Use this to see what activities exist (e.g. when the user has more than one workout in a day) before fetching a specific one.

    Args:
        date: The date to look up. Supports 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day'.
    """
    return await svc_list_workouts_on_date(date)


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
- Use `get_latest_workout` ONLY when the user explicitly wants to fetch/import the single most recent workout from Strava (e.g., "grab my run", "get my latest workout", "import my ride").
- Use `get_workout_by_date` ONLY when the user wants to fetch/import a workout from Strava for a specific date. If the user refers to a particular activity (e.g., "the morning run", "my walk") and there may be more than one activity that day, pass `activity_type` (e.g. 'run', 'walk', 'ride') to select the right one. If a fetch reports multiple activities, retry with `activity_type`.
- Use `list_workouts_on_date` when the user has multiple activities in a day and you need to see the options (names, types, times) before fetching a specific one.
- Use `get_workout_summary` when the user wants to SEE or RETRIEVE an existing workout (e.g., "send me today's workout", "show me my workout", "give me the markdown"). NEVER re-fetch from Strava when the user just wants to see what's already saved.
- Use `update_workout_section` when the user wants to add subjective notes, fueling data, COROS extras, or context. Format the content as markdown matching the template structure:
  - For "Subjective Notes": write the user's notes verbatim as a blockquote. Do NOT split them into pre/during/post or any other sections—preserve their wording and order as given.
  - For "Fueling": use a markdown table with columns Timing, Item, Carbs, Caffeine, Sodium, Water.
  - For "COROS Extras": use a markdown table with Metric and Value columns.
  - For "Context": use a blockquote with the context text.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[
            get_latest_workout,
            get_workout_by_date,
            list_workouts_on_date,
            update_workout_section,
            get_workout_summary,
        ],
        model=agent_model,
    )

    logger.debug(f"Workout agent created with model '{agent_model}'")
    return workout
