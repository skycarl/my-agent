"""
Workout service for formatting Strava data and managing workout files.

Handles fetching from Strava, formatting markdown, file I/O, and notes.
"""

import glob as glob_module
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from app.agents.workout import strava_client
from app.core.settings import config
from app.core.timezone_utils import now_local


METERS_PER_MILE = 1609.34
METERS_TO_FEET = 3.28084


def _format_duration(seconds: int) -> str:
    """Format seconds into H:MM:SS or MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_pace(seconds_per_mile: float) -> str:
    """Format pace as M:SS/mi."""
    minutes = int(seconds_per_mile) // 60
    secs = int(seconds_per_mile) % 60
    return f"{minutes}:{secs:02d}/mi"


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime. Supports 'today', 'yesterday', and YYYY-MM-DD."""
    lower = date_str.strip().lower()
    today = now_local()

    if lower == "today":
        return today
    if lower == "yesterday":
        return today - timedelta(days=1)

    # Try ISO format (YYYY-MM-DD)
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(
            tzinfo=today.tzinfo
        )
    except ValueError:
        pass

    # Try "Month Day" format (e.g., "March 19")
    try:
        parsed = datetime.strptime(date_str.strip(), "%B %d")
        return parsed.replace(year=today.year, tzinfo=today.tzinfo)
    except ValueError:
        pass

    raise ValueError(
        f"Could not parse date '{date_str}'. Use 'today', 'yesterday', 'YYYY-MM-DD', or 'Month Day'."
    )


def _find_workout_file(date_str: str) -> Path | None:
    """Find a workout markdown file matching the given date."""
    target_date = _parse_date(date_str)
    date_prefix = target_date.strftime("%Y-%m-%d")
    pattern = str(Path(config.workouts_path) / f"{date_prefix}-*.md")
    matches = glob_module.glob(pattern)
    return Path(matches[0]) if matches else None


def format_workout_markdown(activity: dict) -> str:
    """Convert a Strava activity dict into a formatted markdown string."""
    # Parse activity date
    start_date = datetime.fromisoformat(activity["start_date_local"])
    date_str = start_date.strftime("%B %d, %Y")

    # Distance
    distance_mi = activity["distance"] / METERS_PER_MILE

    # Time
    moving_time = activity["moving_time"]
    time_str = _format_duration(moving_time)

    # Pace
    pace_seconds = moving_time / distance_mi if distance_mi > 0 else 0
    pace_str = _format_pace(pace_seconds)

    # Elevation
    elevation_ft = activity.get("total_elevation_gain", 0) * METERS_TO_FEET

    # Build summary
    lines = [
        f"# Run — {date_str}",
        "",
        "## Summary",
        f"- Distance: {distance_mi:.1f} mi",
        f"- Time: {time_str}",
        f"- Avg Pace: {pace_str}",
    ]

    if activity.get("average_heartrate"):
        lines.append(f"- Avg HR: {int(activity['average_heartrate'])} bpm")
    if activity.get("max_heartrate"):
        lines.append(f"- Max HR: {int(activity['max_heartrate'])} bpm")

    lines.append(f"- Elevation Gain: {int(elevation_ft)} ft")

    # Splits table
    splits = activity.get("splits_standard", [])
    if splits:
        lines.extend(["", "## Splits", "| Mile | Pace | HR |", "|------|------|----|"])
        for i, split in enumerate(splits, 1):
            split_pace = (
                split["moving_time"] / (split["distance"] / METERS_PER_MILE)
                if split["distance"] > 0
                else 0
            )
            hr = (
                int(split["average_heartrate"])
                if split.get("average_heartrate")
                else "-"
            )
            lines.append(f"| {i} | {_format_pace(split_pace)} | {hr} |")

    lines.append("")
    return "\n".join(lines)


def _workout_file_path(activity: dict) -> Path:
    """Get the file path for a workout based on its activity data."""
    start_date = datetime.fromisoformat(activity["start_date_local"])
    filename = f"{start_date.strftime('%Y-%m-%d')}-{activity['id']}.md"
    return Path(config.workouts_path) / filename


def _save_workout(activity: dict, markdown: str) -> Path:
    """Save workout markdown to file."""
    file_path = _workout_file_path(activity)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(markdown)
    logger.info(f"Workout saved to {file_path}")
    return file_path


async def fetch_latest_workout() -> str:
    """Fetch the latest workout from Strava and save as markdown."""
    activity = await strava_client.get_latest_activity()
    markdown = format_workout_markdown(activity)
    file_path = _save_workout(activity, markdown)

    distance_mi = activity["distance"] / METERS_PER_MILE
    pace_seconds = activity["moving_time"] / distance_mi if distance_mi > 0 else 0

    return (
        f"Saved workout to {file_path.name}: "
        f"{distance_mi:.1f} mi, {_format_duration(activity['moving_time'])}, "
        f"{_format_pace(pace_seconds)}"
    )


async def fetch_workout_by_date(date_str: str) -> str:
    """Fetch a workout from Strava for a specific date and save as markdown."""
    target_date = _parse_date(date_str)
    activity = await strava_client.get_activities_on_date(target_date)

    if activity is None:
        return f"No run found on {target_date.strftime('%B %d, %Y')}."

    markdown = format_workout_markdown(activity)
    file_path = _save_workout(activity, markdown)

    distance_mi = activity["distance"] / METERS_PER_MILE
    pace_seconds = activity["moving_time"] / distance_mi if distance_mi > 0 else 0

    return (
        f"Saved workout to {file_path.name}: "
        f"{distance_mi:.1f} mi, {_format_duration(activity['moving_time'])}, "
        f"{_format_pace(pace_seconds)}"
    )


def add_notes(date_str: str, notes: str) -> str:
    """Append notes to an existing workout file."""
    file_path = _find_workout_file(date_str)
    if file_path is None:
        target_date = _parse_date(date_str)
        return f"No workout file found for {target_date.strftime('%B %d, %Y')}. Fetch the workout first."

    content = file_path.read_text()

    # Format notes as bullet points if not already
    note_lines = []
    for line in notes.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("- "):
            line = f"- {line}"
        if line:
            note_lines.append(line)

    if "## Notes" in content:
        # Append to existing Notes section
        content = content.rstrip() + "\n" + "\n".join(note_lines) + "\n"
    else:
        # Add new Notes section
        content = content.rstrip() + "\n## Notes\n" + "\n".join(note_lines) + "\n"

    file_path.write_text(content)
    logger.info(f"Notes added to {file_path.name}")
    return f"Notes added to {file_path.name}."


def get_workout_summary(date_str: str) -> str:
    """Read and return the full markdown content of a workout file."""
    file_path = _find_workout_file(date_str)
    if file_path is None:
        target_date = _parse_date(date_str)
        return f"No workout file found for {target_date.strftime('%B %d, %Y')}. Fetch the workout first."

    return file_path.read_text()
