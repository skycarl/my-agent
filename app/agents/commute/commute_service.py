"""
Commute service — pure business logic for commute-related queries.

Exposes plain functions that agents call directly via @function_tool.
"""

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from .parse_hours import fetch_hours_rows
from app.core.timezone_utils import now_local


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
    rationale: str = Field(
        "",
        description="The agent's rationale for why the alert was or was not relevant",
    )


class RecentAlertsResponse(BaseModel):
    alerts: List[AlertSummary] = Field(..., description="List of recent alerts")
    total_stored: int = Field(..., description="Total number of alerts in storage")


class MonorailHoursResponse(BaseModel):
    hours: List[str] = Field(..., description="List of monorail operating hours")
    current_date: str = Field(..., description="Current date for context (YYYY-MM-DD)")
    current_day: str = Field(..., description="Current day of the week")


def get_monorail_hours() -> MonorailHoursResponse:
    """Get the current operating hours for the Seattle Monorail."""
    hours = fetch_hours_rows()
    now = now_local()
    current_date = now.strftime("%Y-%m-%d")
    current_day = now.strftime("%A")

    return MonorailHoursResponse(
        hours=hours, current_date=current_date, current_day=current_day
    )


def _parse_legacy_decision(agent_response: str) -> tuple[bool, str]:
    """Extract notify_user/message_content from old alerts that lack top-level fields."""
    notify_user = False
    message_content = ""

    # Try <json> tags (legacy format)
    match = re.search(r"<json>(.*?)</json>", agent_response, re.DOTALL)
    if match:
        try:
            decision = json.loads(match.group(1).strip())
            notify_user = decision.get("notify_user", False)
            message_content = decision.get("message_content", "")
        except json.JSONDecodeError:
            pass
    else:
        # Structured output format: notify_user=True/False
        nu_match = re.search(r"notify_user=(True|False)", agent_response)
        if nu_match:
            notify_user = nu_match.group(1) == "True"
        mc_match = re.search(
            r"message_content='(.*?)'(?:\s|$)", agent_response, re.DOTALL
        )
        if mc_match:
            message_content = mc_match.group(1)

    return notify_user, message_content


def get_recent_alerts(limit: int = 50, days: int = 2) -> RecentAlertsResponse:
    """Get recent commute alerts that were processed by the system.

    Returns all alerts (both relevant and irrelevant) within the given time
    window so the agent has full context when answering user questions.

    Args:
        limit: Maximum number of alerts to return (safety cap).
        days: Only return alerts from the last N days.
    """
    if not ALERTS_FILE.exists():
        return RecentAlertsResponse(alerts=[], total_stored=0)

    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            all_alerts = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return RecentAlertsResponse(alerts=[], total_stored=0)

    total = len(all_alerts)
    cutoff = (now_local() - timedelta(days=days)).isoformat()

    summaries = []
    for alert in all_alerts:
        # Date filter
        received = alert.get("received_date", "")
        if received and received < cutoff:
            continue

        # Prefer structured top-level fields (written since this change)
        if "notify_user" in alert:
            notify_user = alert["notify_user"]
            message_content = alert.get("message_content", "")
        else:
            # Fallback: regex-parse agent_response for old alerts
            agent_response = alert.get("agent_processing", {}).get("agent_response", "")
            notify_user, message_content = _parse_legacy_decision(agent_response or "")

        # Extract rationale from agent processing metadata
        rationale = ""
        agent_response_str = alert.get("agent_processing", {}).get("agent_response", "")
        if agent_response_str:
            rat_match = re.search(
                r"rationale='(.*?)'(?:\s|$)", agent_response_str, re.DOTALL
            )
            if rat_match:
                rationale = rat_match.group(1)

        summaries.append(
            AlertSummary(
                subject=alert.get("subject", ""),
                received_date=alert.get("received_date", ""),
                alert_type=alert.get("alert_type", ""),
                notify_user=notify_user,
                message_content=message_content,
                rationale=rationale,
            )
        )

    return RecentAlertsResponse(alerts=summaries[-limit:], total_stored=total)


def cleanup_old_alerts(retention_days: int = 30) -> int:
    """Remove alerts older than retention_days. Returns count removed."""
    if not ALERTS_FILE.exists():
        return 0

    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            alerts = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return 0

    cutoff = (now_local() - timedelta(days=retention_days)).isoformat()
    active = [a for a in alerts if a.get("stored_date", "") >= cutoff]
    removed = len(alerts) - len(active)

    if removed > 0:
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(active, f, indent=2, ensure_ascii=False, default=str)

    return removed
