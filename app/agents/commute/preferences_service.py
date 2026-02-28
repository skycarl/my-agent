"""
Commute preferences service — manages schedule preferences and ad hoc overrides.

Provides functions for reading/writing the human-readable preferences file
and managing structured override entries with expiry.
"""

import json
import uuid
from pathlib import Path

from app.core.settings import config
from app.core.timezone_utils import now_local


def _preferences_path() -> Path:
    return Path(config.commute_preferences_path)


def _overrides_path() -> Path:
    return Path(config.commute_overrides_path)


def read_preferences_file() -> str:
    """Read and return the full content of the commute preferences file."""
    path = _preferences_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_preferences_file(content: str) -> str:
    """Overwrite the commute preferences file with new content."""
    path = _preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "Commute preferences updated successfully."


def _read_overrides_raw() -> list[dict]:
    """Read raw overrides from JSON file."""
    path = _overrides_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _write_overrides(overrides: list[dict]) -> None:
    """Write overrides list to JSON file."""
    path = _overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, ensure_ascii=False)


def get_commute_overrides() -> list[dict]:
    """Read overrides JSON, filter out expired entries, return active overrides."""
    today = now_local().strftime("%Y-%m-%d")
    overrides = _read_overrides_raw()
    return [o for o in overrides if o.get("expires_after", "") >= today]


def add_commute_override(
    date: str,
    override_type: str,
    note: str,
    expires_after: str | None = None,
) -> dict:
    """Add a commute override entry.

    Args:
        date: The date this override applies to (YYYY-MM-DD).
        override_type: Either "commute_day" or "remote_day".
        note: Human-readable note about the override.
        expires_after: Date after which this override expires (YYYY-MM-DD).
                       Defaults to the same date as `date`.

    Returns:
        The created override entry.
    """
    if override_type not in ("commute_day", "remote_day"):
        raise ValueError(
            f"Invalid override_type: '{override_type}'. Must be 'commute_day' or 'remote_day'."
        )

    entry = {
        "id": str(uuid.uuid4())[:8],
        "date": date,
        "type": override_type,
        "note": note,
        "expires_after": expires_after or date,
        "created_at": now_local().isoformat(),
    }

    overrides = _read_overrides_raw()
    overrides.append(entry)
    _write_overrides(overrides)
    return entry


def remove_commute_override(override_id: str) -> bool:
    """Remove an override entry by ID. Returns True if found and removed."""
    overrides = _read_overrides_raw()
    new_overrides = [o for o in overrides if o.get("id") != override_id]
    if len(new_overrides) == len(overrides):
        return False
    _write_overrides(new_overrides)
    return True


def get_full_commute_context() -> str:
    """Build a full commute context string for injection into agent prompts.

    Reads both the preferences file and active overrides, formats them together
    with today's day-of-week for the agent's convenience.
    """
    now = now_local()
    today_str = now.strftime("%A, %Y-%m-%d")

    preferences = read_preferences_file()
    overrides = get_commute_overrides()

    parts = [f"Today is {today_str}."]

    if preferences:
        parts.append(f"### Commute Preferences\n{preferences.strip()}")
    else:
        parts.append("### Commute Preferences\nNo preferences configured.")

    if overrides:
        parts.append("### Active Overrides")
        for o in overrides:
            parts.append(
                f"- {o['date']}: {o['type']} — {o.get('note', '')} (expires after {o['expires_after']})"
            )
    else:
        parts.append("### Active Overrides\nNo active overrides.")

    return "\n\n".join(parts)


def cleanup_expired_overrides() -> int:
    """Remove overrides where expires_after is in the past. Returns count removed."""
    today = now_local().strftime("%Y-%m-%d")
    overrides = _read_overrides_raw()
    active = [o for o in overrides if o.get("expires_after", "") >= today]
    removed = len(overrides) - len(active)
    if removed > 0:
        _write_overrides(active)
    return removed
