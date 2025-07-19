"""
MCP (Model Context Protocol) client for connecting to local MCP server.

This module provides functionality to connect to the MCP server and fetch available tools.
"""

from typing import Dict, List, Any
from fastmcp import Client
from loguru import logger

from app.core.settings import config


class MCPClient:
    """MCP client wrapper for connecting to local MCP server."""

    def __init__(self):
        """Initialize the MCP client."""
        self._client = None
        self._tools_cache = None
        self._tools_cache_timestamp = None
        logger.debug("MCP client initialized")

    def is_enabled(self) -> bool:
        """Check if MCP tools integration is enabled."""
        return config.enable_mcp_tools

    async def get_client(self) -> Client:
        """Get the MCP client instance."""
        if self._client is None:
            self._client = Client(config.mcp_server_url)
            logger.debug(f"MCP client instance created for {config.mcp_server_url}")
        return self._client

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools from the MCP server.

        Returns:
            List of tool definitions compatible with OpenAI function calling format
        """
        if not self.is_enabled():
            logger.debug("MCP tools integration is disabled")
            return []

        try:
            client = await self.get_client()
            async with client:
                # Get tools from MCP server
                tools = await client.list_tools()
                logger.debug(f"Retrieved {len(tools)} tools from MCP server")

                # Convert MCP tools to OpenAI Responses API format
                openai_tools = []
                for tool in tools:
                    openai_tool = {
                        "type": "function",
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    }
                    openai_tools.append(openai_tool)

                self._tools_cache = openai_tools
                logger.debug(f"Converted {len(openai_tools)} tools to OpenAI format")
                return openai_tools

        except Exception as e:
            logger.warning(f"Failed to get tools from MCP server: {str(e)}")
            logger.debug(f"MCP server error details: {e}", exc_info=True)
            return []

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool response from the MCP server
        """
        if not self.is_enabled():
            logger.debug("MCP tools integration is disabled")
            return {"error": "MCP tools integration is disabled"}

        try:
            client = await self.get_client()
            async with client:
                logger.debug(
                    f"Calling MCP tool: {tool_name} with arguments: {arguments}"
                )

                # Call the tool
                result = await client.call_tool(tool_name, arguments)

                logger.debug(f"MCP tool {tool_name} returned: {result}")

                # Convert result to dict format
                if hasattr(result, "content"):
                    # If result has content, extract it
                    if isinstance(result.content, list) and len(result.content) > 0:
                        # Get the first content item and safely extract text
                        content_item = result.content[0]
                        # Try to get text attribute safely
                        try:
                            text_content = getattr(content_item, "text", None)
                            if text_content:
                                return {"content": text_content}
                        except AttributeError:
                            pass
                        # Fallback to string representation
                        return {"content": str(content_item)}
                    else:
                        return {"content": str(result.content)}
                else:
                    # Fallback: convert to string
                    return {"content": str(result)}

        except Exception as e:
            logger.warning(f"Failed to call MCP tool {tool_name}: {str(e)}")
            logger.debug(f"MCP tool call error details: {e}", exc_info=True)
            return {"error": f"Failed to call tool {tool_name}: {str(e)}"}

    async def close(self):
        """Close the MCP client connection."""
        if self._client:
            # FastMCP Client doesn't have explicit close method
            # but we can clear the reference
            self._client = None
            logger.debug("MCP client connection closed")


# Create a global MCP client instance
mcp_client = MCPClient()
