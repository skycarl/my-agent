"""
Shared helpers for persisting and reloading scheduled tasks.

Provides append_task_to_config used by both API endpoints and Agent tools.
"""

import json
from pathlib import Path
from typing import Any, Dict

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

    # ID
    task_id = new_task_data.get("id") or f"task_{len(data.get('tasks', [])) + 1}"
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


