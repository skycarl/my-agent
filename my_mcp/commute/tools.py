"""
Commute-related tools for FastMCP server.
"""

from typing import List
from pydantic import BaseModel, Field
from fastmcp import FastMCP

from .parse_hours import fetch_hours_rows
from ..utils.date_utils import get_current_date_info


class MonorailHoursResponse(BaseModel):
    hours: List[str] = Field(..., description="List of monorail operating hours")
    current_date: str = Field(..., description="Current date for context (YYYY-MM-DD)")
    current_day: str = Field(..., description="Current day of the week")


def register_commute_tools(server: FastMCP):
    """Register all commute tools with the FastMCP server."""

    @server.tool
    def get_monorail_hours() -> MonorailHoursResponse:
        """Get the current operating hours for the Seattle Monorail.

        Fetches the latest hours from the Seattle Monorail website and returns
        the operating schedule for each day of the week. Includes current date
        context to help understand "today" and "tomorrow" references.

        Returns:
            List of monorail operating hours for each day, plus current date context.

        Raises:
            RuntimeError: If there's an error fetching the hours from the website.
        """
        try:
            hours = fetch_hours_rows()
            current_date, current_day, _, _ = get_current_date_info()

            return MonorailHoursResponse(
                hours=hours, current_date=current_date, current_day=current_day
            )
        except Exception as e:
            raise RuntimeError(f"Failed to fetch monorail hours: {str(e)}")
