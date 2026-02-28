"""
Management tools for listing and deleting scheduled tasks.

Kept separate from add tool to minimize schema complexity.
"""

from typing import Optional

from agents import function_tool
from loguru import logger

from app.core.scheduler import scheduler_service
from app.core.task_store import (
    list_tasks_from_config,
    delete_task_by_id,
    toggle_task_by_id,
)


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
        tasks = list_tasks_from_config(
            only_enabled=only_enabled, name_filter=name_filter
        )

        if not tasks:
            return "No scheduled tasks found."

        lines: list[str] = []
        for t in tasks:
            name = str(t.get("name", ""))
            enabled = bool(t.get("enabled", True))
            schedule = t.get("schedule", {}) or {}
            s_type = schedule.get("type", "?")

            if s_type == "cron":
                expr = schedule.get("expression", "")
                try:
                    from cron_descriptor import ExpressionDescriptor

                    schedule_desc = str(ExpressionDescriptor(expr))
                except Exception:
                    schedule_desc = f"cron: {expr}"
            elif s_type == "interval":
                schedule_desc = f"every {schedule.get('interval_seconds', '?')}s"
            elif s_type == "date":
                raw = schedule.get("run_at", "")
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(raw)
                    schedule_desc = (
                        f"one-time: {dt.strftime('%b %-d, %Y at %-I:%M %p')}"
                    )
                except Exception:
                    schedule_desc = f"one-time: {raw or '?'}"
            else:
                schedule_desc = s_type

            status = "enabled" if enabled else "DISABLED"
            lines.append(f"- {name} ({status}) — {schedule_desc}")
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
        exact_matches = [
            t for t in all_tasks if str(t.get("name", "")).lower() == name.lower()
        ]
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


@function_tool
async def toggle_scheduled_task(name: str) -> str:
    """Enable or disable a scheduled task by its human-friendly name.

    Toggles the task's enabled state (enabled → disabled, disabled → enabled).
    """
    try:
        all_tasks = list_tasks_from_config()
        exact_matches = [
            t for t in all_tasks if str(t.get("name", "")).lower() == name.lower()
        ]
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
        new_state = toggle_task_by_id(task_id)
        if new_state is None:
            return f"Task not found: {task.get('name')} [{task_id}]"

        scheduler_service.reload_configuration()
        state_label = "enabled" if new_state else "disabled"
        logger.info(f"Agent tool toggled scheduled task: {task_id} → {state_label}")
        return f"{task.get('name')} is now {state_label}."
    except Exception as e:
        logger.error(f"Failed to toggle scheduled task via tool: {e}")
        return f"Error: {str(e)}"
