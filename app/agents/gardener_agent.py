"""
Gardener agent for handling garden-related queries using MCP tools.

This agent specializes in garden management tasks and uses MCP tools
to interact with the garden database.
"""

from typing import Any, Dict

from agents import Agent, function_tool
from loguru import logger
from app.core.mcp_client import mcp_client
from app.core.settings import config


async def _call_mcp(tool_name: str, args: Dict[str, Any]) -> str:
    """Call an MCP tool and return the result as a string."""
    try:
        result = await mcp_client.call_tool(tool_name, args)
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}"
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            return content if isinstance(content, str) else str(content)
        return str(result)
    except Exception as e:
        logger.error(f"Error calling {tool_name} MCP tool: {e}")
        return f"Error calling {tool_name}: {e}"


@function_tool
async def get_plants() -> str:
    """Get a list of all plants in the garden with their yields."""
    return await _call_mcp("get_plants", {})


@function_tool
async def add_plant(plant_name: str) -> str:
    """
    Add a new plant to the garden.

    Args:
        plant_name: Name of the plant to add
    """
    return await _call_mcp("add_plant", {"plant_name": plant_name})


@function_tool
async def get_produce_counts(plant_name: str) -> str:
    """
    Get harvest statistics for a specific plant.

    Args:
        plant_name: Name of the plant to get stats for
    """
    return await _call_mcp("get_produce_counts", {"plant_name": plant_name})


@function_tool
async def add_produce(plant_name: str, amount: float, notes: str = "") -> str:
    """
    Record a new harvest for a plant.

    Args:
        plant_name: Name of the plant being harvested
        amount: Numeric amount harvested (e.g., 5, 10.5)
        notes: Optional notes about the harvest
    """
    args = {"plant_name": plant_name, "amount": amount}
    if notes:
        args["notes"] = notes
    return await _call_mcp("add_produce", args)


def create_gardener_agent(model: str = None) -> Agent:
    """
    Create a Gardener agent with MCP tools.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Gardener agent
    """
    # Use provided model or fall back to default
    agent_model = model or config.default_model

    gardener = Agent(
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

    When adding harvest information, the user will provide a statement like: "I harvested 10 tomatoes." In this scenario, you should first use the `get_plants` tool to get the plant names available in the garden. Then, you should use the `add_produce` tool to add the harvest information. Use this information to disambiguate the plant name if needed (such as plural/singular variations, or names with typos).
    
    If a user asks about plants that don't exist, then suggest they check what plants are available first.
    
    Provide clear, actionable responses about their garden management tasks.
    Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
    """,
        tools=[get_plants, add_plant, get_produce_counts, add_produce],
        model=agent_model,
    )

    logger.debug(
        f"Gardener agent created with model '{agent_model}' and MCP tools integration"
    )
    return gardener
