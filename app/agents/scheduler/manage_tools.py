"""
Management tools for listing, deleting, toggling, editing,
and running scheduled tasks.
"""

from typing import Optional

from agents import function_tool
from loguru import logger

from app.core.scheduler import scheduler_service
from app.core.task_store import (
    list_tasks_from_config,
    delete_task_by_id,
    toggle_task_by_id,
    update_task_schedule,
)


def _find_task_by_name(name: str) -> tuple[Optional[dict], Optional[str]]:
    """Find a single task by name. Returns (task_dict, error_message)."""
    all_tasks = list_tasks_from_config()
    exact = [t for t in all_tasks if str(t.get("name", "")).lower() == name.lower()]
    candidates = exact or [
        t for t in all_tasks if name.lower() in str(t.get("name", "")).lower()
    ]

    if len(candidates) == 0:
        return None, f"No task found with name '{name}'."
    if len(candidates) > 1:
        names = ", ".join([f"{t.get('name')} ({t.get('id')})" for t in candidates])
        return None, f"Multiple tasks match '{name}'. Candidates: {names}"
    return candidates[0], None


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
        task, err = _find_task_by_name(name)
        if err:
            return err

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
        task, err = _find_task_by_name(name)
        if err:
            return err

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


@function_tool
async def edit_scheduled_task(
    name: str,
    schedule_type: str,
    cron_expression: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    run_at: Optional[str] = None,
) -> str:
    """Update the schedule of an existing task by its human-friendly name.

    Provide the new schedule_type and its corresponding field:
    - schedule_type="cron" → cron_expression (e.g. "30 19 * * 1,2")
    - schedule_type="interval" → interval_seconds
    - schedule_type="date" → run_at as ISO-8601 string
    """
    try:
        task, err = _find_task_by_name(name)
        if err:
            return err

        task_id = str(task.get("id"))
        new_schedule = update_task_schedule(
            task_id,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_at=run_at,
        )
        if new_schedule is None:
            return f"Task not found: {task.get('name')} [{task_id}]"

        scheduler_service.reload_configuration()
        logger.info(f"Agent tool updated schedule for task: {task_id}")
        return f"Updated {task.get('name')} schedule to {schedule_type}."
    except Exception as e:
        logger.error(f"Failed to edit scheduled task via tool: {e}")
        return f"Error: {str(e)}"


@function_tool
async def run_scheduled_task_now(name: str) -> str:
    """Run a scheduled task immediately by its human-friendly name.

    Triggers the task's action right now without waiting for its schedule.
    The task's schedule is not affected.
    """
    try:
        task, err = _find_task_by_name(name)
        if err:
            return err

        task_name = task.get("name", "")
        task_id = str(task.get("id"))

        # Build a TaskConfig from the raw dict so task_manager can execute it
        from app.models.tasks import TaskConfig

        task_config = TaskConfig(**task)

        from app.core.task_manager import task_manager

        result = await task_manager.execute_task(task_config)

        if result.success:
            logger.info(f"Agent tool ran task immediately: {task_id}")
            return f"Ran {task_name} successfully."
        else:
            return f"Ran {task_name} but it failed: {result.error_message or 'unknown error'}"
    except Exception as e:
        logger.error(f"Failed to run scheduled task via tool: {e}")
        return f"Error: {str(e)}"
