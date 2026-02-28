"""
Commute-related tools for FastMCP server.
"""

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from fastmcp import FastMCP

from .parse_hours import fetch_hours_rows
from ..utils.date_utils import get_current_date_info


ALERTS_FILE = Path("storage/commute_alerts.json")


class AlertSummary(BaseModel):
    subject: str = Field(..., description="Alert subject line")
    received_date: str = Field(..., description="When the alert was received")
    alert_type: str = Field(..., description="Type of alert (e.g. email)")
    notify_user: bool = Field(
        ..., description="Whether the agent decided to notify the user"
    )
    message_content: str = Field(
        ...,
        description="The notification message sent to the user (empty if not notified)",
    )


class RecentAlertsResponse(BaseModel):
    alerts: List[AlertSummary] = Field(..., description="List of recent alerts")
    total_stored: int = Field(..., description="Total number of alerts in storage")


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

    @server.tool
    def get_recent_alerts(limit: int = 5) -> RecentAlertsResponse:
        """Get recent commute alerts that were processed by the system.

        Returns the most recent alerts with their subject, received date,
        and the agent's notification decision.

        Args:
            limit: Maximum number of recent alerts to return (default 5).

        Returns:
            Recent alerts with summaries and total count.
        """
        if not ALERTS_FILE.exists():
            return RecentAlertsResponse(alerts=[], total_stored=0)

        try:
            with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                all_alerts = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return RecentAlertsResponse(alerts=[], total_stored=0)

        total = len(all_alerts)
        recent = all_alerts[-limit:]

        summaries = []
        for alert in recent:
            agent_processing = alert.get("agent_processing", {})
            agent_response = agent_processing.get("agent_response", "")

            # Try to extract notification decision from agent response JSON
            notify_user = False
            message_content = ""
            if agent_response:
                import re

                match = re.search(r"<json>(.*?)</json>", agent_response, re.DOTALL)
                if match:
                    try:
                        decision = json.loads(match.group(1).strip())
                        notify_user = decision.get("notify_user", False)
                        message_content = decision.get("message_content", "")
                    except json.JSONDecodeError:
                        pass

            summaries.append(
                AlertSummary(
                    subject=alert.get("subject", ""),
                    received_date=alert.get("received_date", ""),
                    alert_type=alert.get("alert_type", ""),
                    notify_user=notify_user,
                    message_content=message_content,
                )
            )

        return RecentAlertsResponse(alerts=summaries, total_stored=total)
