"""
Shared helpers for persisting and reloading scheduled tasks.

Provides append_task_to_config used by both API endpoints and Agent tools.
Also provides utilities for listing and deleting tasks from config storage.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core.settings import config
from app.core.timezone_utils import now_local, parse_datetime_in_scheduler_tz


def append_task_to_config(new_task_data: Dict[str, Any]) -> str:
    """
    Append a task to the scheduled_tasks.json and return the task id.

    - Light validation here; strict validation happens when scheduler loads Pydantic models
    - Auto-generates id if not provided
    - Normalizes date schedule run_at into ISO-8601 string in scheduler timezone
    - Updates last_modified
    """
    storage_file = Path(config.tasks_config_path)
    storage_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    if storage_file.exists():
        try:
            data = json.loads(storage_file.read_text(encoding="utf-8"))
        except Exception:
            data = {"version": "1.0", "tasks": []}
    else:
        data = {"version": "1.0", "tasks": []}

    # ID (use UUIDs to avoid collisions even after deletions)
    task_id = new_task_data.get("id") or uuid.uuid4().hex
    new_task_data["id"] = task_id

    # Normalize date schedule run_at if present
    schedule = new_task_data.get("schedule", {})
    if schedule.get("type") == "date" and schedule.get("run_at") is not None:
        try:
            run_at_dt = parse_datetime_in_scheduler_tz(schedule["run_at"])
            schedule["run_at"] = run_at_dt.isoformat()
            new_task_data["schedule"] = schedule
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Append and write
    data.setdefault("tasks", []).append(new_task_data)
    data["last_modified"] = now_local().isoformat()
    storage_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return task_id


def _read_storage_file() -> Dict[str, Any]:
    """Internal helper to read tasks storage file, returning a dict structure."""
    storage_file = Path(config.tasks_config_path)
    if storage_file.exists():
        try:
            return json.loads(storage_file.read_text(encoding="utf-8"))
        except Exception:
            return {"version": "1.0", "tasks": []}
    return {"version": "1.0", "tasks": []}


def load_tasks_config() -> Dict[str, Any]:
    """Load and return the entire tasks configuration dict from storage."""
    return _read_storage_file()


def list_tasks_from_config(
    only_enabled: bool = False, name_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List tasks from the configuration storage with optional filters.

    Args:
        only_enabled: If True, return only tasks where enabled is True
        name_filter: Optional substring match against task name (case-insensitive)

    Returns:
        List of task dicts as stored in configuration
    """
    data = _read_storage_file()
    tasks: List[Dict[str, Any]] = data.get("tasks", [])

    if only_enabled:
        tasks = [t for t in tasks if t.get("enabled", True)]

    if name_filter:
        lowered = name_filter.lower()
        tasks = [t for t in tasks if str(t.get("name", "")).lower().find(lowered) != -1]

    return tasks


def delete_task_by_id(task_id: str) -> bool:
    """
    Delete a task by its ID from the configuration storage.

    Returns True if a task was removed, False if not found.
    """
    storage_file = Path(config.tasks_config_path)
    data = _read_storage_file()
    original_len = len(data.get("tasks", []))
    data["tasks"] = [t for t in data.get("tasks", []) if t.get("id") != task_id]

    if len(data.get("tasks", [])) == original_len:
        return False

    data["last_modified"] = now_local().isoformat()
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    storage_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return True
