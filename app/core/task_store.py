"""
Shared helpers for persisting and reloading scheduled tasks.

Provides append_task_to_config used by both API endpoints and Agent tools.
Also provides utilities for listing and deleting tasks from config storage.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from filelock import FileLock
from loguru import logger

from app.core.settings import config
from app.core.timezone_utils import now_local, parse_datetime_in_scheduler_tz
from app.models.tasks import TaskConfig


def get_config_lock_path() -> str:
    """Return the path for the file lock protecting scheduled_tasks.json."""
    return config.tasks_config_path + ".lock"


def _validate_task(task_data: Dict[str, Any]) -> None:
    """Validate a task dict against TaskConfig before persisting.

    One invalid task in scheduled_tasks.json makes the whole file unloadable
    (TasksConfiguration parses all tasks at once), which silently freezes
    every scheduler reload — so nothing invalid may ever be written.

    Raises ValueError with a readable message on invalid input.
    """
    try:
        TaskConfig(**task_data)
    except Exception as e:
        raise ValueError(f"Invalid task configuration: {e}")


def _write_storage_file(data: Dict[str, Any]) -> None:
    """Write the tasks storage file atomically (temp file + rename)."""
    storage_file = Path(config.tasks_config_path)
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = storage_file.with_suffix(".json.tmp")
    tmp_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp_file, storage_file)


def _read_storage_file() -> Dict[str, Any]:
    """Internal helper to read tasks storage file, returning a dict structure."""
    storage_file = Path(config.tasks_config_path)
    if storage_file.exists():
        try:
            return json.loads(storage_file.read_text(encoding="utf-8"))
        except Exception as e:
            # Preserve the corrupt file for manual recovery instead of
            # letting the next write silently replace all tasks with an
            # empty list.
            backup = storage_file.with_suffix(".json.corrupt")
            logger.error(
                f"Tasks config file is unreadable ({e}); backing it up to {backup}"
            )
            try:
                os.replace(storage_file, backup)
            except OSError as backup_err:
                logger.error(f"Failed to back up corrupt tasks config: {backup_err}")
            return {"version": "1.0", "tasks": []}
    return {"version": "1.0", "tasks": []}


def append_task_to_config(new_task_data: Dict[str, Any]) -> str:
    """
    Append a task to the scheduled_tasks.json and return the task id.

    - Validates the task against TaskConfig before persisting
    - Auto-generates id if not provided
    - Normalizes date schedule run_at into ISO-8601 string in scheduler timezone
    - Updates last_modified
    """
    with FileLock(get_config_lock_path()):
        data = _read_storage_file()

        # ID (use UUIDs to avoid collisions even after deletions)
        task_id = new_task_data.get("id") or uuid.uuid4().hex
        if any(t.get("id") == task_id for t in data.get("tasks", [])):
            raise HTTPException(
                status_code=409,
                detail=f"A task with id '{task_id}' already exists",
            )
        new_task_data["id"] = task_id

        # Normalize date schedule run_at if present
        schedule = new_task_data.get("schedule", {})
        if schedule.get("type") == "date" and schedule.get("run_at") is not None:
            try:
                run_at_dt = parse_datetime_in_scheduler_tz(schedule["run_at"])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
            # A past run_at would be silently dropped by APScheduler once
            # outside the misfire grace, leaving the task stuck forever
            if run_at_dt <= now_local():
                raise HTTPException(
                    status_code=400,
                    detail=f"run_at must be in the future (got {run_at_dt.isoformat()})",
                )
            schedule["run_at"] = run_at_dt.isoformat()
            new_task_data["schedule"] = schedule

        try:
            _validate_task(new_task_data)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Append and write
        data.setdefault("tasks", []).append(new_task_data)
        data["last_modified"] = now_local().isoformat()
        _write_storage_file(data)

        return task_id


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


def toggle_task_by_id(task_id: str) -> Optional[bool]:
    """
    Toggle a task's enabled state by its ID.

    Returns the new enabled value, or None if the task was not found.
    """
    with FileLock(get_config_lock_path()):
        data = _read_storage_file()
        for t in data.get("tasks", []):
            if t.get("id") == task_id:
                t["enabled"] = not t.get("enabled", True)
                data["last_modified"] = now_local().isoformat()
                _write_storage_file(data)
                return t["enabled"]
        return None


def update_task_schedule(
    task_id: str,
    schedule_type: str,
    cron_expression: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    run_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update a task's schedule by its ID.

    Returns the updated schedule dict, or None if the task was not found.
    Raises ValueError if the new schedule is invalid (e.g. cron type without
    a valid cron expression).
    """
    with FileLock(get_config_lock_path()):
        data = _read_storage_file()
        for t in data.get("tasks", []):
            if t.get("id") == task_id:
                if schedule_type == "cron":
                    from croniter import croniter

                    if not cron_expression or not croniter.is_valid(cron_expression):
                        raise ValueError(
                            f"A valid cron expression is required for a cron "
                            f"schedule (got: {cron_expression!r})"
                        )
                    schedule = {"type": "cron", "expression": cron_expression}
                elif schedule_type == "interval":
                    if not interval_seconds or int(interval_seconds) < 1:
                        raise ValueError(
                            "interval_seconds (>= 1) is required for an interval schedule"
                        )
                    schedule = {
                        "type": "interval",
                        "interval_seconds": int(interval_seconds),
                    }
                elif schedule_type == "date":
                    if not run_at:
                        raise ValueError("run_at is required for a date schedule")
                    dt = parse_datetime_in_scheduler_tz(run_at)
                    schedule = {"type": "date", "run_at": dt.isoformat()}
                else:
                    return None

                updated_task = {**t, "schedule": schedule}
                _validate_task(updated_task)

                t["schedule"] = schedule
                data["last_modified"] = now_local().isoformat()
                _write_storage_file(data)
                return schedule
        return None


def delete_task_by_id(task_id: str) -> bool:
    """
    Delete a task by its ID from the configuration storage.

    Returns True if a task was removed, False if not found.
    """
    with FileLock(get_config_lock_path()):
        data = _read_storage_file()
        original_len = len(data.get("tasks", []))
        data["tasks"] = [t for t in data.get("tasks", []) if t.get("id") != task_id]

        if len(data.get("tasks", [])) == original_len:
            return False

        data["last_modified"] = now_local().isoformat()
        _write_storage_file(data)
        return True
