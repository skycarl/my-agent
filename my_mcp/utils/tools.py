"""
General utility tools for FastMCP server.
"""

from pydantic import BaseModel, Field
from fastmcp import FastMCP

from .date_utils import get_current_date_info


class CurrentDateResponse(BaseModel):
    current_date: str = Field(..., description="Current date in YYYY-MM-DD format")
    current_day: str = Field(
        ..., description="Current day of the week (e.g., Monday, Tuesday)"
    )
    current_time: str = Field(..., description="Current time in HH:MM format (24-hour)")
    timezone: str = Field(..., description="Timezone information")


def register_utils_tools(server: FastMCP):
    """Register all utility tools with the FastMCP server."""

    @server.tool
    def get_current_date() -> CurrentDateResponse:
        """Get the current date and time information.

        This tool provides the current date, day of the week, and time in Seattle timezone.
        Use this when you need to understand what "today" or "tomorrow" refers to.

        Returns:
            Current date information including date, day, time, and timezone.
        """
        current_date, current_day, current_time, timezone_info = get_current_date_info()

        return CurrentDateResponse(
            current_date=current_date,
            current_day=current_day,
            current_time=current_time,
            timezone=timezone_info,
        )
