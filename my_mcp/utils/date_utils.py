"""
Date and time utility functions for the MCP server.
"""

from datetime import datetime
import pytz


def get_current_date_info() -> tuple[str, str, str, str]:
    """Get current date information for context in Seattle time.

    Returns:
        Tuple of (current_date, current_day, current_time, timezone_info)
        - current_date: YYYY-MM-DD format
        - current_day: Full day name (Monday, Tuesday, etc.)
        - current_time: HH:MM format (24-hour)
        - timezone_info: "Pacific Time"
    """
    # Get Seattle timezone
    seattle_tz = pytz.timezone("America/Los_Angeles")
    now = datetime.now(seattle_tz)

    current_date = now.strftime("%Y-%m-%d")
    current_day = now.strftime("%A")  # Full day name (Monday, Tuesday, etc.)
    current_time = now.strftime("%H:%M")
    timezone_info = "Pacific Time"

    return current_date, current_day, current_time, timezone_info
