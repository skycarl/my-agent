"""
Action logging service for CSV-based action tracking.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path

from app.core.settings import config
from app.core.timezone_utils import now_local, now_local_isoformat

HEADERS = ["timestamp", "action", "latitude", "longitude"]


def _get_csv_path() -> Path:
    return Path(config.action_log_path)


def log_action(action: str, latitude: float | None, longitude: float | None) -> str:
    """
    Log an action to the CSV file.

    Returns:
        Confirmation message string.
    """
    csv_path = _get_csv_path()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADERS)

        timestamp = now_local_isoformat()
        writer.writerow(
            [
                timestamp,
                action,
                latitude if latitude is not None else "",
                longitude if longitude is not None else "",
            ]
        )

    location_str = f"{latitude}, {longitude}" if latitude is not None else "unavailable"
    return f"Logged '{action}' at {timestamp} (location: {location_str})"


def query_action_log(action: str | None = None, days: int | None = None) -> str:
    """
    Query the action log with optional filters.

    Args:
        action: Filter by action name (case-insensitive). None = all actions.
        days: Filter to entries from the last N days. None = all time.

    Returns:
        Formatted summary string.
    """
    csv_path = _get_csv_path()

    if not csv_path.exists():
        return "No action log entries found."

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return "No action log entries found."

    # Filter by action name
    if action:
        rows = [r for r in rows if r["action"].lower() == action.lower()]

    # Filter by date range
    if days is not None:
        cutoff = now_local() - timedelta(days=days)
        filtered = []
        for row in rows:
            try:
                row_dt = datetime.fromisoformat(row["timestamp"])
                if row_dt >= cutoff:
                    filtered.append(row)
            except (ValueError, KeyError):
                continue
        rows = filtered

    if not rows:
        filter_desc = []
        if action:
            filter_desc.append(f"action='{action}'")
        if days is not None:
            filter_desc.append(f"last {days} days")
        return f"No entries found matching: {', '.join(filter_desc)}."

    # Build summary
    lines = [f"Found {len(rows)} entries:"]
    for row in rows[-20:]:  # Show last 20 entries max
        location = ""
        if row.get("latitude") and row.get("longitude"):
            location = f" ({row['latitude']}, {row['longitude']})"
        lines.append(f"  - {row['timestamp']}: {row['action']}{location}")

    if len(rows) > 20:
        lines.append(f"  ... and {len(rows) - 20} more entries")

    return "\n".join(lines)
