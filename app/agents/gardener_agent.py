"""
Gardener agent for handling garden-related queries.

This agent specializes in garden management tasks and uses direct tool calls
to interact with the garden database.
"""

from decimal import Decimal

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.gardener.garden_service import (
    get_plants as svc_get_plants,
    add_plant as svc_add_plant,
    get_produce_counts as svc_get_produce_counts,
    add_produce as svc_add_produce,
)
from app.core.settings import config


@function_tool
async def get_plants() -> str:
    """Get a list of all plants in the garden with their yields."""
    result = svc_get_plants()
    return str(result)


@function_tool
async def add_plant(plant_name: str) -> str:
    """
    Add a new plant to the garden.

    Args:
        plant_name: Name of the plant to add
    """
    result = svc_add_plant(plant_name)
    return str(result)


@function_tool
async def get_produce_counts(plant_name: str) -> str:
    """
    Get harvest statistics for a specific plant.

    Args:
        plant_name: Name of the plant to get stats for
    """
    result = svc_get_produce_counts(plant_name)
    return str(result.model_dump())


@function_tool
async def add_produce(plant_name: str, amount: float, notes: str = "") -> str:
    """
    Record a new harvest for a plant.

    Args:
        plant_name: Name of the plant being harvested
        amount: Numeric amount harvested (e.g., 5, 10.5)
        notes: Optional notes about the harvest
    """
    result = svc_add_produce(plant_name, Decimal(str(amount)), notes if notes else None)
    return str(result)


def create_gardener_agent(model: str = None) -> Agent:
    """
    Create a Gardener agent with direct tool calls.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Gardener agent
    """
    agent_model = model or config.default_model

    gardener = Agent(
        name="Gardener",
        handoff_description="Handles garden management: tracking plants, recording harvests, and viewing garden statistics.",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are a specialized garden management assistant. You help users track plants, record harvests, view garden statistics, and add new plants.

When adding harvest information (e.g., "I harvested 10 tomatoes"), first use `get_plants` to get available plant names, then use `add_produce` to record it. Use the plant list to disambiguate names (plural/singular, typos).

If a user asks about plants that don't exist, suggest they check what plants are available first.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[get_plants, add_plant, get_produce_counts, add_produce],
        model=agent_model,
    )

    logger.debug(f"Gardener agent created with model '{agent_model}'")
    return gardener
