"""
Scheduler tools for OpenAI Agents to add tasks to the scheduler.

These tools wrap the shared task store and scheduler reload to provide
an easy, robust interface for agents to schedule both recurring and one-time tasks.
"""

from typing import Any, Dict, Literal, Optional

from agents import function_tool
from loguru import logger

from app.core.scheduler import scheduler_service
from app.core.task_store import append_task_to_config


@function_tool
async def add_scheduled_task(
    name: str,
    task_type: Literal["api_call"],
    schedule_type: Literal["cron", "interval", "date"],
    # Schedule specifics (provide the ones relevant to the schedule_type)
    cron_expression: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    run_at: Optional[str] = None,
    # Optional general task fields
    description: Optional[str] = None,
    enabled: bool = True,
    task_id: Optional[str] = None,
    # API call configuration
    api_endpoint: Optional[str] = None,
    api_method: Literal["GET", "POST", "PUT"] = "POST",
    api_payload: Optional[Dict[str, Any]] = None,
    api_headers: Optional[Dict[str, str]] = None,
    api_timeout: Optional[int] = None,
    # Retry behavior
    max_retries: Optional[int] = None,
    retry_delay: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Add a scheduled task that can be cron, interval, or a one-time date task.

    Usage guidelines:
    - schedule_type="cron" → provide cron_expression like "30 19 * * 1,2"
    - schedule_type="interval" → provide interval_seconds
    - schedule_type="date" → provide run_at as ISO-8601 string. If timezone is omitted, it
      will be interpreted in the app's default timezone. Example: "2025-09-01T09:00:00".

    For task_type:
    - "api_call" → provide api_* fields

    Returns a dict with {success, task_id, message}.
    """
    try:
        # Build schedule
        if schedule_type == "cron":
            if not cron_expression:
                raise ValueError(
                    "cron_expression is required when schedule_type='cron'"
                )
            schedule = {"type": "cron", "expression": cron_expression}
        elif schedule_type == "interval":
            if not interval_seconds:
                raise ValueError(
                    "interval_seconds is required when schedule_type='interval'"
                )
            schedule = {"type": "interval", "interval_seconds": int(interval_seconds)}
        elif schedule_type == "date":
            if not run_at:
                raise ValueError("run_at is required when schedule_type='date'")
            schedule = {"type": "date", "run_at": run_at}
        else:
            raise ValueError(
                "schedule_type must be one of: 'cron', 'interval', or 'date'"
            )

        # Build base task
        new_task: Dict[str, Any] = {
            "id": task_id,
            "name": name,
            "type": task_type,
            "enabled": enabled,
            "description": description,
            "schedule": schedule,
        }

        # Configure task-specific fields
        if task_type == "api_call":
            if not api_endpoint:
                raise ValueError("api_endpoint is required for api_call tasks")
            new_task["api_call"] = {
                "endpoint": api_endpoint,
                "method": api_method or "POST",
                "payload": api_payload or {},
                "headers": api_headers or None,
                "timeout": api_timeout or 30,
            }
        else:
            raise ValueError("task_type must be 'api_call'")

        if max_retries is not None:
            new_task["max_retries"] = int(max_retries)
        if retry_delay is not None:
            new_task["retry_delay"] = int(retry_delay)

        # Persist and reload scheduler
        created_id = append_task_to_config(new_task)
        scheduler_service.reload_configuration()

        logger.info(f"Agent tool scheduled task created: {created_id}")
        return {
            "success": True,
            "task_id": created_id,
            "message": "Task added and scheduler reloaded",
        }

    except Exception as e:
        logger.error(f"Failed to add scheduled task via tool: {e}")
        return {"success": False, "task_id": "", "message": str(e)}
