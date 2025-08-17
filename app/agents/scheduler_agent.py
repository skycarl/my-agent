"""
Scheduler agent for converting natural-language scheduling requests into tasks.

This agent uses the add_scheduled_task tool to create scheduled API calls
to the application's /agent_response endpoint.
"""

from agents import Agent, function_tool
from loguru import logger
from app.core.settings import config


@function_tool
async def schedule_task(
    name: str,
    schedule_type: str,  # "cron" | "interval" | "date"
    cron_expression: str | None = None,
    interval_seconds: int | None = None,
    run_at: str | None = None,
    description: str | None = None,
    api_method: str = "POST",
    instruction: str = "",
) -> str:
    """Schedule an API call to /agent_response using the scheduler service.

    Avoids importing the function-decorated tool (which uses a non-strict schema)
    by writing to the task store directly and reloading the scheduler.
    """
    try:
        # Build schedule
        if schedule_type == "cron":
            if not cron_expression:
                return "Error: cron_expression is required for cron schedule"
            schedule = {"type": "cron", "expression": cron_expression}
        elif schedule_type == "interval":
            if interval_seconds is None:
                return "Error: interval_seconds is required for interval schedule"
            schedule = {"type": "interval", "interval_seconds": int(interval_seconds)}
        elif schedule_type == "date":
            if not run_at:
                return "Error: run_at is required for date schedule"
            schedule = {"type": "date", "run_at": run_at}
        else:
            return "Error: schedule_type must be one of: cron, interval, date"

        # Build task configuration (api_call only, endpoint allowlist enforced)
        new_task = {
            "id": None,
            "name": name,
            "type": "api_call",
            "enabled": True,
            "description": description,
            "schedule": schedule,
            "api_call": {
                "endpoint": "/agent_response",
                "method": api_method or "POST",
                "payload": {"input": instruction} if instruction else {},
                "headers": None,
                "timeout": 120,
            },
            # Avoid duplicate user notifications from retries on long-running agent calls
            "max_retries": 0,
            "retry_delay": 60,
        }

        # Persist and reload scheduler
        from app.core.task_store import append_task_to_config  # local import
        from app.core.scheduler import scheduler_service  # local import

        append_task_to_config(new_task)
        scheduler_service.reload_configuration()

        # Short confirmation
        if schedule_type == "cron":
            return f"Scheduled with cron {cron_expression}."
        if schedule_type == "interval":
            return f"Scheduled every {int(interval_seconds)} seconds."
        return f"Scheduled for {run_at}."
    except Exception as e:
        return f"Error: {str(e)}"


def create_scheduler_agent(model: str = None) -> Agent:
    """
    Create the Scheduler agent that turns user requests into scheduled tasks.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Scheduler agent
    """
    agent_model = model or config.default_model

    scheduler = Agent(
        name="Scheduler",
        instructions="""You are the Scheduler. You convert clear natural-language instructions into scheduled tasks using the add_scheduled_task tool.

Supported schedule types:
- cron: Produce a standard 5-field cron expression (min hour day month weekday). Example: "30 19 * * 2".
- interval: Provide interval_seconds as an integer (e.g., 900 for every 15 minutes).
- date: Provide run_at as an ISO-8601 timestamp. Timezone may be omitted and app defaults will apply (e.g., "2025-09-01T09:00:00").

Task requirements:
- Always use task_type="api_call".
- Only schedule calls to api_endpoint="/agent_response".
- For typical reminders, set api_method="POST" and api_payload={"input": "<the user's instruction>"}.

Clarifying questions:
- If any required detail (date, time, or recurrence pattern) is missing or ambiguous, ask a brief, direct clarifying question. Continue asking follow-ups until you have what you need.

Tool usage and responses:
- Use add_scheduled_task to create the schedule.
- After a successful tool call (success=true), reply with a concise confirmation of what was scheduled and when it will run. Do not include any task_id.
  Examples:
  - "Scheduled for Sep 1 at 9:00 AM."
  - "Scheduled every 15 minutes."
  - "Scheduled every Tuesday at 7:30 PM."
- If the tool returns an error (success=false), briefly state the error message and do not attempt recovery.

Important:
- Only schedule /agent_response calls. Do not schedule other endpoints.
- If the user's instruction is immediately schedulable, schedule directly without unnecessary questions.
""",
        tools=[schedule_task],
        model=agent_model,
    )

    logger.debug(
        f"Scheduler agent created with model '{agent_model}' and the add_scheduled_task tool"
    )
    return scheduler


