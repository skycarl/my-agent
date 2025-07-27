"""
Commute assistant agent for handling commuting-related queries using MCP tools.

This agent specializes in commute information and uses MCP tools
to provide transportation-related assistance.
"""

from agents import Agent, function_tool
from loguru import logger
from app.core.mcp_client import mcp_client
from app.core.settings import config


@function_tool
async def get_monorail_hours() -> str:
    """Get the current operating hours for the Seattle Monorail."""
    try:
        result = await mcp_client.call_tool("get_monorail_hours", {})
        if isinstance(result, dict) and "error" in result:
            return f"Error getting monorail hours: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling get_monorail_hours MCP tool: {e}")
        return f"Error getting monorail hours: {str(e)}"


@function_tool
async def get_current_date() -> str:
    """Get the current date and time information to understand context for transportation schedules."""
    try:
        result = await mcp_client.call_tool("get_current_date", {})
        if isinstance(result, dict) and "error" in result:
            return f"Error getting current date: {result['error']}"
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Error calling get_current_date MCP tool: {e}")
        return f"Error getting current date: {str(e)}"


# Create the Commute agent with MCP tools
commute_agent = Agent(
    name="Commute Assistant",
    instructions="""You are a specialized commute and transportation assistant. You help users with:
    
    1. Seattle Monorail operating hours and schedules
    2. General commuting information and assistance
    3. Transportation planning and timing questions
    4. Current date/time context for transportation schedules
    
    You have access to tools that provide:
    - get_monorail_hours: Get current Seattle Monorail operating hours for each day
    - get_current_date: Get current date and time information for context
    
    When users ask about transportation schedules, always consider:
    - What day it is today (always use get_current_date to get the current date)
    - Current operating hours (use get_monorail_hours for monorail info)
    - Help users understand when services are available
    
    Be helpful and provide clear, actionable transportation information.
    If users ask about transportation options not covered by your tools, provide general guidance
    and suggest they check official transportation websites for the most current information.
    Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
    """,
    tools=[get_monorail_hours, get_current_date],
    model=config.valid_openai_models[0]
    if config.valid_openai_models
    else "gpt-4o-mini",
)

logger.debug("Commute agent created with MCP tools integration")
