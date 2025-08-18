"""
Management tools for listing and deleting scheduled tasks.

Kept separate from add tool to minimize schema complexity.
"""

from typing import Optional

from agents import function_tool
from loguru import logger

from app.core.scheduler import scheduler_service
from app.core.task_store import list_tasks_from_config, delete_task_by_id


@function_tool
async def list_scheduled_tasks(
    only_enabled: bool = False, name_filter: Optional[str] = None
) -> str:
    """List scheduled tasks from the configuration storage.

    Filters:
    - only_enabled: return only enabled tasks
    - name_filter: case-insensitive substring match on task name
    """
    try:
        tasks = list_tasks_from_config(only_enabled=only_enabled, name_filter=name_filter)

        if not tasks:
            return "No scheduled tasks found."

        lines: list[str] = []
        for t in tasks:
            name = str(t.get("name", ""))
            tid = str(t.get("id", ""))
            enabled = bool(t.get("enabled", True))
            schedule = t.get("schedule", {}) or {}
            s_type = schedule.get("type", "?")
            extra = (
                schedule.get("expression")
                or str(schedule.get("interval_seconds"))
                or schedule.get("run_at")
                or ""
            )
            lines.append(f"- {name} [{tid}] {'ENABLED' if enabled else 'DISABLED'} ({s_type} {extra})")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Failed to list scheduled tasks via tool: {e}")
        return f"Error: {str(e)}"


@function_tool
async def delete_scheduled_task(name: str) -> str:
    """Delete a scheduled task by its human-friendly name.

    - If exactly one task matches name (case-insensitive exact match preferred), delete it
    - If multiple match, return error listing candidates for disambiguation
    - If none match, return not found
    """
    try:
        all_tasks = list_tasks_from_config()
        exact_matches = [t for t in all_tasks if str(t.get("name", "")).lower() == name.lower()]
        candidates = exact_matches or [
            t for t in all_tasks if name.lower() in str(t.get("name", "")).lower()
        ]

        if len(candidates) == 0:
            return f"No task found with name '{name}'."
        if len(candidates) > 1:
            names = ", ".join([f"{t.get('name')} ({t.get('id')})" for t in candidates])
            return f"Multiple tasks match name '{name}'. Candidates: {names}"

        task = candidates[0]
        task_id = str(task.get("id"))
        removed = delete_task_by_id(task_id)
        if not removed:
            return f"Task not found or already removed: {task.get('name')} [{task_id}]"

        scheduler_service.reload_configuration()
        logger.info(f"Agent tool deleted scheduled task: {task_id}")
        return f"Deleted: {task.get('name')} [{task_id}]"
    except Exception as e:
        logger.error(f"Failed to delete scheduled task via tool: {e}")
        return f"Error: {str(e)}"


