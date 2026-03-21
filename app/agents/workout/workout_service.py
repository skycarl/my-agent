"""
Workout service for formatting Strava data and managing workout files.

Handles fetching from Strava, formatting markdown for Run/Ride/Strength
activity types, file I/O, and structured notes sections.
"""

import glob as glob_module
import re
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from app.agents.workout import strava_client
from app.core.settings import config
from app.core.timezone_utils import now_local


METERS_PER_MILE = 1609.34
METERS_TO_FEET = 3.28084

# Activity types that are "runs" for template selection
RUN_TYPES = {"Run", "TrailRun", "Treadmill", "VirtualRun"}
RIDE_TYPES = {"Ride", "VirtualRide", "MountainBikeRide", "GravelRide", "EBikeRide"}

# Workout type mapping from Strava
WORKOUT_TYPE_MAP = {
    0: "Easy",
    1: "Race",
    2: "Long Run",
    3: "Workout",
}


def _format_duration(seconds: int | float) -> str:
    """Format seconds into H:MM:SS or M:SS."""
    seconds = int(seconds)
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


def _speed_to_pace(meters_per_second: float) -> str:
    """Convert m/s to M:SS/mi pace string."""
    if meters_per_second <= 0:
        return "-"
    seconds_per_mile = METERS_PER_MILE / meters_per_second
    return _format_pace(seconds_per_mile)


def _speed_to_mph(meters_per_second: float) -> str:
    """Convert m/s to mph."""
    mph = meters_per_second * 3600 / METERS_PER_MILE
    return f"{mph:.1f} mph"


def _celsius_to_fahrenheit(celsius: float) -> int:
    """Convert Celsius to Fahrenheit."""
    return int(celsius * 9 / 5 + 32)


def _slugify(name: str) -> str:
    """Convert activity name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


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
    pattern = str(Path(config.workouts_path) / f"{date_prefix}_*.md")
    matches = glob_module.glob(pattern)
    return Path(matches[0]) if matches else None


def _get_activity_type(activity: dict) -> str:
    """Determine if activity is 'run', 'ride', or 'other'."""
    sport_type = activity.get("sport_type") or activity.get("type", "")
    if sport_type in RUN_TYPES:
        return "run"
    if sport_type in RIDE_TYPES:
        return "ride"
    return "other"


def _guess_workout_category(activity: dict) -> str:
    """Auto-suggest workout category from Strava workout_type."""
    wtype = activity.get("workout_type")
    return WORKOUT_TYPE_MAP.get(wtype, "Easy")


def _format_elev_delta(meters: float) -> str:
    """Format elevation difference in feet with +/- sign."""
    feet = int(meters * METERS_TO_FEET)
    if feet >= 0:
        return f"+{feet} ft"
    return f"{feet} ft"


# ---------------------------------------------------------------------------
# Summary table helpers
# ---------------------------------------------------------------------------


def _summary_row(label: str, value) -> str:
    return f"| {label} | {value} |"


def _build_run_summary(activity: dict) -> list[str]:
    """Build the summary table rows for a run activity."""
    distance_mi = activity["distance"] / METERS_PER_MILE
    moving_time = activity["moving_time"]
    elapsed_time = activity.get("elapsed_time", moving_time)
    avg_speed = activity.get("average_speed", 0)
    max_speed = activity.get("max_speed", 0)

    rows = [
        _summary_row("Distance", f"{distance_mi:.2f} mi"),
        _summary_row("Moving Time", _format_duration(moving_time)),
        _summary_row("Elapsed Time", _format_duration(elapsed_time)),
        _summary_row("Avg Pace", _speed_to_pace(avg_speed) if avg_speed else "-"),
    ]

    # Best mile — find fastest split_standard with full mile distance
    splits = activity.get("splits_standard", [])
    full_mile_splits = [
        s for s in splits if s.get("distance", 0) > METERS_PER_MILE * 0.95
    ]
    if full_mile_splits:
        best_pace = min(
            s["moving_time"] / (s["distance"] / METERS_PER_MILE)
            for s in full_mile_splits
            if s.get("distance", 0) > 0
        )
        rows.append(_summary_row("Best Mile", _format_pace(best_pace)))

    rows.append(
        _summary_row("Avg Speed", _speed_to_mph(avg_speed) if avg_speed else "-")
    )
    rows.append(
        _summary_row("Max Speed", _speed_to_mph(max_speed) if max_speed else "-")
    )

    if activity.get("average_heartrate"):
        rows.append(_summary_row("Avg HR", f"{int(activity['average_heartrate'])} bpm"))
    if activity.get("max_heartrate"):
        rows.append(_summary_row("Max HR", f"{int(activity['max_heartrate'])} bpm"))
    if activity.get("average_cadence"):
        rows.append(
            _summary_row("Avg Cadence", f"{int(activity['average_cadence'] * 2)} spm")
        )
    if activity.get("max_cadence"):
        rows.append(
            _summary_row("Max Cadence", f"{int(activity['max_cadence'] * 2)} spm")
        )
    if activity.get("average_watts"):
        rows.append(_summary_row("Avg Power", f"{int(activity['average_watts'])} W"))
    if activity.get("calories"):
        rows.append(_summary_row("Calories", f"{int(activity['calories'])} kcal"))

    elev_gain = activity.get("total_elevation_gain", 0) * METERS_TO_FEET
    rows.append(_summary_row("Elev Gain", f"{int(elev_gain)} ft"))
    if activity.get("elev_high") is not None:
        # Compute elev loss from splits (Strava doesn't give it directly)
        if splits:
            loss_m = sum(
                abs(s.get("elevation_difference", 0))
                for s in splits
                if s.get("elevation_difference", 0) < 0
            )
            rows.append(_summary_row("Elev Loss", f"{int(loss_m * METERS_TO_FEET)} ft"))
        rows.append(
            _summary_row(
                "Elev High", f"{int(activity['elev_high'] * METERS_TO_FEET)} ft"
            )
        )
    if activity.get("elev_low") is not None:
        rows.append(
            _summary_row("Elev Low", f"{int(activity['elev_low'] * METERS_TO_FEET)} ft")
        )

    if activity.get("average_temp") is not None:
        rows.append(
            _summary_row(
                "Avg Temp", f"{_celsius_to_fahrenheit(activity['average_temp'])}°F"
            )
        )
    rows.append(_summary_row("Trainer", "Yes" if activity.get("trainer") else "No"))
    if activity.get("device_name"):
        rows.append(_summary_row("Device", activity["device_name"]))

    return rows


def _build_ride_summary(activity: dict) -> list[str]:
    """Build the summary table rows for a ride activity."""
    distance_mi = activity["distance"] / METERS_PER_MILE
    moving_time = activity["moving_time"]
    elapsed_time = activity.get("elapsed_time", moving_time)
    avg_speed = activity.get("average_speed", 0)
    max_speed = activity.get("max_speed", 0)

    rows = [
        _summary_row("Distance", f"{distance_mi:.2f} mi"),
        _summary_row("Moving Time", _format_duration(moving_time)),
        _summary_row("Elapsed Time", _format_duration(elapsed_time)),
        _summary_row("Avg Speed", _speed_to_mph(avg_speed) if avg_speed else "-"),
        _summary_row("Max Speed", _speed_to_mph(max_speed) if max_speed else "-"),
    ]

    if activity.get("average_heartrate"):
        rows.append(_summary_row("Avg HR", f"{int(activity['average_heartrate'])} bpm"))
    if activity.get("max_heartrate"):
        rows.append(_summary_row("Max HR", f"{int(activity['max_heartrate'])} bpm"))
    if activity.get("average_watts"):
        rows.append(_summary_row("Avg Power", f"{int(activity['average_watts'])} W"))
    if activity.get("max_watts"):
        rows.append(_summary_row("Max Power", f"{int(activity['max_watts'])} W"))
    if activity.get("weighted_average_watts"):
        rows.append(
            _summary_row(
                "Weighted Avg Power (NP)",
                f"{int(activity['weighted_average_watts'])} W",
            )
        )
    if activity.get("average_cadence"):
        rows.append(
            _summary_row("Avg Cadence", f"{int(activity['average_cadence'])} rpm")
        )
    if activity.get("max_cadence"):
        rows.append(_summary_row("Max Cadence", f"{int(activity['max_cadence'])} rpm"))
    if activity.get("kilojoules"):
        rows.append(_summary_row("Total Work", f"{int(activity['kilojoules'])} kJ"))
    if activity.get("calories"):
        rows.append(_summary_row("Calories", f"{int(activity['calories'])} kcal"))

    elev_gain = activity.get("total_elevation_gain", 0) * METERS_TO_FEET
    rows.append(_summary_row("Elev Gain", f"{int(elev_gain)} ft"))

    if activity.get("average_temp") is not None:
        rows.append(
            _summary_row(
                "Avg Temp", f"{_celsius_to_fahrenheit(activity['average_temp'])}°F"
            )
        )
    rows.append(_summary_row("Trainer", "Yes" if activity.get("trainer") else "No"))
    if activity.get("device_name"):
        rows.append(_summary_row("Device", activity["device_name"]))

    return rows


def _build_other_summary(activity: dict) -> list[str]:
    """Build summary table rows for strength/cross-training activities."""
    moving_time = activity.get("moving_time", 0)
    rows = [_summary_row("Duration", _format_duration(moving_time))]

    if activity.get("average_heartrate"):
        rows.append(_summary_row("Avg HR", f"{int(activity['average_heartrate'])} bpm"))
    if activity.get("max_heartrate"):
        rows.append(_summary_row("Max HR", f"{int(activity['max_heartrate'])} bpm"))
    if activity.get("calories"):
        rows.append(_summary_row("Calories", f"{int(activity['calories'])} kcal"))

    return rows


# ---------------------------------------------------------------------------
# Splits / Laps / Zones / Best Efforts
# ---------------------------------------------------------------------------


def _format_mile_splits(activity: dict) -> list[str]:
    """Format mile splits table for run activities."""
    splits = activity.get("splits_standard", [])
    if not splits:
        return []

    lines = [
        "",
        "## Mile Splits",
        "| Mile | Time | Pace | Avg HR | Elev Δ | GAP | Pace Zone |",
        "|------|------|------|--------|--------|-----|-----------|",
    ]

    for i, split in enumerate(splits, 1):
        dist = split.get("distance", 0)
        split_mi = dist / METERS_PER_MILE
        time_str = _format_duration(split["moving_time"])

        # Pace from average_speed if available, else compute
        if split.get("average_speed") and split["average_speed"] > 0:
            pace = _speed_to_pace(split["average_speed"])
        elif dist > 0:
            pace = _format_pace(split["moving_time"] / split_mi)
        else:
            pace = "-"

        hr = int(split["average_heartrate"]) if split.get("average_heartrate") else "-"
        elev = _format_elev_delta(split.get("elevation_difference", 0))

        # GAP (grade adjusted pace)
        if (
            split.get("average_grade_adjusted_speed")
            and split["average_grade_adjusted_speed"] > 0
        ):
            gap = _speed_to_pace(split["average_grade_adjusted_speed"])
        else:
            gap = "-"

        pace_zone = split.get("pace_zone", "-")

        # Display fractional mile for the last split if < 1 mile
        mile_label = str(i) if split_mi >= 0.95 else f"{split_mi:.2f}"

        lines.append(
            f"| {mile_label} | {time_str} | {pace} | {hr} | {elev} | {gap} | {pace_zone} |"
        )

    return lines


def _format_laps(laps: list[dict], activity_type: str) -> list[str]:
    """Format laps table. Only include if >1 lap."""
    if not laps or len(laps) <= 1:
        return []

    lines = ["", "## Laps"]

    if activity_type == "run":
        lines.append(
            "| Lap | Name | Distance | Time | Pace | Avg HR | Max HR | Avg Cadence | Avg Power | Elev Gain |"
        )
        lines.append(
            "|-----|------|----------|------|------|--------|--------|-------------|-----------|-----------|"
        )
        for i, lap in enumerate(laps, 1):
            dist_mi = lap.get("distance", 0) / METERS_PER_MILE
            time_str = _format_duration(lap.get("moving_time", 0))
            pace = (
                _speed_to_pace(lap["average_speed"])
                if lap.get("average_speed")
                else "-"
            )
            avg_hr = (
                int(lap["average_heartrate"]) if lap.get("average_heartrate") else "-"
            )
            max_hr = int(lap["max_heartrate"]) if lap.get("max_heartrate") else "-"
            cadence = (
                f"{int(lap['average_cadence'] * 2)} spm"
                if lap.get("average_cadence")
                else "-"
            )
            power = (
                f"{int(lap['average_watts'])} W" if lap.get("average_watts") else "-"
            )
            elev = f"{int(lap.get('total_elevation_gain', 0) * METERS_TO_FEET)} ft"
            name = lap.get("name", f"Lap {i}")
            lines.append(
                f"| {i} | {name} | {dist_mi:.2f} mi | {time_str} | {pace} | {avg_hr} | {max_hr} | {cadence} | {power} | {elev} |"
            )
    else:
        # Ride laps
        lines.append(
            "| Lap | Name | Distance | Time | Avg Power | Avg HR | Max HR | Avg Cadence |"
        )
        lines.append(
            "|-----|------|----------|------|-----------|--------|--------|-------------|"
        )
        for i, lap in enumerate(laps, 1):
            dist_mi = lap.get("distance", 0) / METERS_PER_MILE
            time_str = _format_duration(lap.get("moving_time", 0))
            power = (
                f"{int(lap['average_watts'])} W" if lap.get("average_watts") else "-"
            )
            avg_hr = (
                int(lap["average_heartrate"]) if lap.get("average_heartrate") else "-"
            )
            max_hr = int(lap["max_heartrate"]) if lap.get("max_heartrate") else "-"
            cadence = (
                f"{int(lap['average_cadence'])} rpm"
                if lap.get("average_cadence")
                else "-"
            )
            name = lap.get("name", f"Lap {i}")
            lines.append(
                f"| {i} | {name} | {dist_mi:.2f} mi | {time_str} | {power} | {avg_hr} | {max_hr} | {cadence} |"
            )

    return lines


def _format_hr_zones(zones_data: list[dict]) -> list[str]:
    """Format HR zone distribution table."""
    hr_zones = None
    for zone_group in zones_data:
        if zone_group.get("type") == "heartrate":
            hr_zones = zone_group
            break

    if not hr_zones or not hr_zones.get("distribution_buckets"):
        return []

    zone_names = {
        1: "Recovery",
        2: "Aerobic",
        3: "Tempo",
        4: "Threshold",
        5: "Anaerobic",
    }
    buckets = hr_zones["distribution_buckets"]
    total_seconds = sum(b.get("time", 0) for b in buckets)
    if total_seconds == 0:
        return []

    lines = [
        "",
        "## HR Zones",
        "| Zone | Name | Min HR | Max HR | Time | % of Total |",
        "|------|------|--------|--------|------|------------|",
    ]

    for i, bucket in enumerate(buckets, 1):
        name = zone_names.get(i, f"Zone {i}")
        min_hr = bucket.get("min", 0)
        max_hr = bucket.get("max", 0)
        time_secs = bucket.get("time", 0)
        pct = int(time_secs / total_seconds * 100) if total_seconds else 0
        min_str = "—" if min_hr == 0 else str(min_hr)
        max_str = "—" if max_hr == -1 or max_hr == 0 else str(max_hr)
        lines.append(
            f"| {i} | {name} | {min_str} | {max_str} | {_format_duration(time_secs)} | {pct}% |"
        )

    return lines


def _format_power_zones(zones_data: list[dict]) -> list[str]:
    """Format power zone distribution table (rides only)."""
    power_zones = None
    for zone_group in zones_data:
        if zone_group.get("type") == "power":
            power_zones = zone_group
            break

    if not power_zones or not power_zones.get("distribution_buckets"):
        return []

    buckets = power_zones["distribution_buckets"]
    total_seconds = sum(b.get("time", 0) for b in buckets)
    if total_seconds == 0:
        return []

    lines = [
        "",
        "## Power Zones",
        "| Zone | Min W | Max W | Time | % of Total |",
        "|------|-------|-------|------|------------|",
    ]

    for i, bucket in enumerate(buckets, 1):
        min_w = bucket.get("min", 0)
        max_w = bucket.get("max", 0)
        time_secs = bucket.get("time", 0)
        pct = int(time_secs / total_seconds * 100) if total_seconds else 0
        min_str = "—" if min_w == 0 else str(min_w)
        max_str = "—" if max_w == -1 or max_w == 0 else str(max_w)
        lines.append(
            f"| {i} | {min_str} | {max_str} | {_format_duration(time_secs)} | {pct}% |"
        )

    return lines


def _format_best_efforts(activity: dict) -> list[str]:
    """Format best efforts table (runs only)."""
    efforts = activity.get("best_efforts", [])
    if not efforts:
        return []

    lines = [
        "",
        "## Best Efforts",
        "| Distance | Time | Pace |",
        "|----------|------|------|",
    ]

    for effort in efforts:
        name = effort.get("name", "")
        elapsed = effort.get("elapsed_time", 0)
        dist = effort.get("distance", 0)
        time_str = _format_duration(elapsed)
        if dist > 0:
            pace = _format_pace(elapsed / (dist / METERS_PER_MILE))
        else:
            pace = "-"
        lines.append(f"| {name} | {time_str} | {pace} |")

    return lines


# ---------------------------------------------------------------------------
# Main format function
# ---------------------------------------------------------------------------


def format_workout_markdown(
    activity: dict,
    zones: list[dict] | None = None,
    laps: list[dict] | None = None,
) -> str:
    """Convert Strava activity data into a structured markdown string."""
    start_date = datetime.fromisoformat(activity["start_date_local"])
    date_str = start_date.strftime("%Y-%m-%d")
    day_of_week = start_date.strftime("%A")
    activity_type = _get_activity_type(activity)
    sport_type = activity.get("sport_type") or activity.get("type", "Unknown")

    # Header
    lines = [
        f"# {activity.get('name', 'Workout')}",
        f"**Date:** {date_str} ({day_of_week})",
        f"**Type:** {activity.get('type', 'Unknown')}",
        f"**Sport Type:** {sport_type}",
    ]

    if activity_type in ("run", "ride"):
        lines.append(f"**Workout Category:** {_guess_workout_category(activity)}")

    # Gear
    gear = activity.get("gear")
    if gear and gear.get("name"):
        lines.append(f"**Gear:** {gear['name']}")

    # Summary table
    lines.extend(["", "## Summary", "| Metric | Value |", "|---|---|"])
    if activity_type == "run":
        lines.extend(_build_run_summary(activity))
    elif activity_type == "ride":
        lines.extend(_build_ride_summary(activity))
    else:
        lines.extend(_build_other_summary(activity))

    # Mile Splits (runs only)
    if activity_type == "run":
        lines.extend(_format_mile_splits(activity))

    # Laps (any type, only if >1)
    if laps:
        lines.extend(_format_laps(laps, activity_type))

    # HR Zones
    if zones:
        lines.extend(_format_hr_zones(zones))

    # Power Zones (rides only)
    if zones and activity_type == "ride":
        lines.extend(_format_power_zones(zones))

    # Best Efforts (runs only)
    if activity_type == "run":
        lines.extend(_format_best_efforts(activity))

    # Placeholder sections for manual input
    lines.extend(
        [
            "",
            "## Subjective Notes",
            "**Pre-run:**",
            "> ",
            "",
            "**During:**",
            "> ",
            "",
            "**Post-run:**",
            "> ",
        ]
    )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------


def _workout_file_path(activity: dict) -> Path:
    """Get the file path for a workout based on its activity data."""
    start_date = datetime.fromisoformat(activity["start_date_local"])
    name_slug = _slugify(activity.get("name", "workout"))
    filename = f"{start_date.strftime('%Y-%m-%d')}_{name_slug}.md"
    return Path(config.workouts_path) / filename


def _save_workout(activity: dict, markdown: str) -> Path:
    """Save workout markdown to file. Skips if file already exists to preserve manual edits."""
    file_path = _workout_file_path(activity)
    if file_path.exists():
        logger.info(f"Workout file already exists at {file_path}, skipping save")
        return file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(markdown)
    logger.info(f"Workout saved to {file_path}")
    return file_path


def _build_summary_message(activity: dict, file_path: Path) -> str:
    """Build a concise summary message for the user."""
    activity_type = _get_activity_type(activity)
    distance_mi = activity["distance"] / METERS_PER_MILE

    if activity_type == "run":
        avg_speed = activity.get("average_speed", 0)
        pace = _speed_to_pace(avg_speed) if avg_speed else "N/A"
        return (
            f"Saved {activity.get('name', 'workout')} to {file_path.name}: "
            f"{distance_mi:.1f} mi, {_format_duration(activity['moving_time'])}, {pace}"
        )
    elif activity_type == "ride":
        return (
            f"Saved {activity.get('name', 'workout')} to {file_path.name}: "
            f"{distance_mi:.1f} mi, {_format_duration(activity['moving_time'])}"
        )
    else:
        return (
            f"Saved {activity.get('name', 'workout')} to {file_path.name}: "
            f"{_format_duration(activity['moving_time'])}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_latest_workout() -> str:
    """Fetch the latest workout from Strava and save as markdown."""
    activity = await strava_client.get_latest_activity()
    zones = await strava_client.get_activity_zones(activity["id"])
    laps = await strava_client.get_activity_laps(activity["id"])
    markdown = format_workout_markdown(activity, zones=zones, laps=laps)
    file_path = _save_workout(activity, markdown)
    return _build_summary_message(activity, file_path)


async def fetch_workout_by_date(date_str: str) -> str:
    """Fetch a workout from Strava for a specific date and save as markdown."""
    target_date = _parse_date(date_str)
    activity = await strava_client.get_activities_on_date(target_date)

    if activity is None:
        return f"No activity found on {target_date.strftime('%B %d, %Y')}."

    zones = await strava_client.get_activity_zones(activity["id"])
    laps = await strava_client.get_activity_laps(activity["id"])
    markdown = format_workout_markdown(activity, zones=zones, laps=laps)
    file_path = _save_workout(activity, markdown)
    return _build_summary_message(activity, file_path)


def update_section(date_str: str, section: str, content: str) -> str:
    """Update or create a specific section in a workout file.

    Supported sections: Subjective Notes, Fueling, COROS Extras, Context.
    For Subjective Notes, content should include the pre/during/post structure.
    """
    file_path = _find_workout_file(date_str)
    if file_path is None:
        target_date = _parse_date(date_str)
        return f"No workout file found for {target_date.strftime('%B %d, %Y')}. Fetch the workout first."

    file_content = file_path.read_text()
    section_header = f"## {section}"

    # Find the section boundaries
    pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
    match = re.search(pattern, file_content, re.DOTALL)

    if match:
        # Replace existing section content
        new_section = f"{section_header}\n{content.strip()}\n"
        file_content = (
            file_content[: match.start()] + new_section + file_content[match.end() :]
        )
    else:
        # Append new section
        file_content = (
            file_content.rstrip() + f"\n\n{section_header}\n{content.strip()}\n"
        )

    file_path.write_text(file_content)
    logger.info(f"Section '{section}' updated in {file_path.name}")
    return f"Section '{section}' updated in {file_path.name}."


def get_workout_summary(date_str: str) -> str:
    """Read and return the full markdown content of a workout file."""
    file_path = _find_workout_file(date_str)
    if file_path is None:
        target_date = _parse_date(date_str)
        return f"No workout file found for {target_date.strftime('%B %d, %Y')}. Fetch the workout first."

    return file_path.read_text()
