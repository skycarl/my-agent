"""
Gardener agent for handling garden-related queries using MCP tools.

This agent specializes in garden management tasks and uses MCP tools
to interact with the garden database.
"""

from agents import Agent, function_tool
from loguru import logger
from app.core.mcp_client import mcp_client
from app.core.settings import config


@function_tool
async def get_plants() -> str:
    """Get a list of all plants in the garden with their yields."""
    try:
        result = await mcp_client.call_tool("get_plants", {})
        if isinstance(result, dict) and "error" in result:
            return f"Error getting plants: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling get_plants MCP tool: {e}")
        return f"Error getting plants: {str(e)}"


@function_tool
async def add_plant(plant_name: str, description: str = "") -> str:
    """
    Add a new plant to the garden.

    Args:
        plant_name: Name of the plant to add
        description: Optional description of the plant
    """
    try:
        args = {"plant_name": plant_name}
        if description:
            args["description"] = description

        result = await mcp_client.call_tool("add_plant", args)
        if isinstance(result, dict) and "error" in result:
            return f"Error adding plant: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling add_plant MCP tool: {e}")
        return f"Error adding plant: {str(e)}"


@function_tool
async def get_produce_counts(plant_name: str) -> str:
    """
    Get harvest statistics for a specific plant.

    Args:
        plant_name: Name of the plant to get stats for
    """
    try:
        result = await mcp_client.call_tool(
            "get_produce_counts", {"plant_name": plant_name}
        )
        if isinstance(result, dict) and "error" in result:
            return f"Error getting produce counts: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling get_produce_counts MCP tool: {e}")
        return f"Error getting produce counts: {str(e)}"


@function_tool
async def add_produce(plant_name: str, amount: str, notes: str = "") -> str:
    """
    Record a new harvest for a plant.

    Args:
        plant_name: Name of the plant being harvested
        amount: Amount harvested (with units, e.g., "5 pounds", "10 tomatoes")
        notes: Optional notes about the harvest
    """
    try:
        args = {"plant_name": plant_name, "amount": amount}
        if notes:
            args["notes"] = notes

        result = await mcp_client.call_tool("add_produce", args)
        if isinstance(result, dict) and "error" in result:
            return f"Error adding produce: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling add_produce MCP tool: {e}")
        return f"Error adding produce: {str(e)}"


# Create the Gardener agent with MCP tools
gardener_agent = Agent(
    name="Gardener",
    instructions="""You are a specialized garden management assistant. You help users:
    
    1. Track plants in their garden
    2. Record harvest information
    3. View garden statistics and history
    4. Add new plants to their garden
    
    You have access to tools that interact with the garden database:
    - get_plants: List all plants and their information
    - add_plant: Add a new plant to the garden
    - get_produce_counts: Get harvest statistics for a plant
    - add_produce: Record a new harvest
    
    When users ask about plants that don't exist, always suggest they check what plants are available first.
    Be helpful and encouraging about their gardening activities.
    Provide clear, actionable responses about their garden management tasks.
    """,
    tools=[get_plants, add_plant, get_produce_counts, add_produce],
    model=config.valid_openai_models[0]
    if config.valid_openai_models
    else "gpt-4o-mini",
)

logger.debug("Gardener agent created with MCP tools integration")
