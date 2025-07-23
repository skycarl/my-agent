"""
Main entry point for the MCP server.
"""

from urllib.parse import urlparse
from fastmcp import FastMCP
from .garden.tools import register_garden_tools
from .commute.tools import register_commute_tools
from .utils.tools import register_utils_tools

# Import the config from the main app
try:
    from app.core.settings import config
except ImportError as e:
    raise ImportError(
        f"Failed to import app.core.settings.config: {e}. Make sure the app package is available."
    )

# Initialize FastMCP server
server = FastMCP(name="my-mcp-server")

# Register garden tools
register_garden_tools(server)

# Register commute tools
register_commute_tools(server)

# Register utils tools
register_utils_tools(server)


def create_app():
    """Create the FastMCP application."""
    return server


if __name__ == "__main__":
    # print("Starting MCP Server on port 8001...")

    # Get host and port from MCP_SERVER_URL
    if not config.mcp_server_url:
        raise ValueError("MCP_SERVER_URL is not configured in settings")

    # Parse the URL to extract host and port
    parsed_url = urlparse(config.mcp_server_url)
    host = parsed_url.hostname or "0.0.0.0"
    port = parsed_url.port or 8001

    # Run FastMCP server using HTTP transport
    server.run(transport="http", host=host, port=port)
    # server.run()
