"""
Scheduler agent for converting natural-language scheduling requests into tasks.

This agent uses the add_scheduled_task tool to create scheduled API calls
to the application's /agent_response endpoint.
"""

from agents import Agent, function_tool
from loguru import logger
from app.core.settings import config
from app.agents.scheduler.manage_tools import (
    list_scheduled_tasks,
    delete_scheduled_task,
)


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
    mode: str = "agent",  # "agent" | "notify"
) -> str:
    """Schedule a task using the scheduler service.

    mode="agent" routes through the full agent pipeline via /agent_response.
    mode="notify" sends a Telegram message directly (no agent processing).
    """
    try:
        if mode not in ("agent", "notify"):
            return "Error: mode must be 'agent' or 'notify'"

        # Build schedule
        if schedule_type == "cron":
            if not cron_expression:
                return "Error: cron_expression is required for cron schedule"
            from croniter import croniter

            if not croniter.is_valid(cron_expression):
                return f"Error: Invalid cron expression '{cron_expression}'"
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

        # Build task configuration
        new_task: dict = {
            "id": None,
            "name": name,
            "type": "api_call",
            "mode": mode,
            "enabled": True,
            "description": description,
            "schedule": schedule,
            # Avoid duplicate user notifications from retries on long-running agent calls
            "max_retries": 0,
            "retry_delay": 60,
        }

        if mode == "notify":
            new_task["notification"] = {
                "message": instruction,
                "parse_mode": "HTML",
            }
        else:
            new_task["api_call"] = {
                "endpoint": "/agent_response",
                "method": api_method or "POST",
                "payload": {"input": instruction} if instruction else {},
                "headers": None,
                "timeout": 120,
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
        instructions="""You are the Scheduler. You convert clear natural-language instructions into scheduled tasks using the schedule_task tool.

Execution modes:
- mode="notify" — Sends a message directly to the user via Telegram. Use for simple reminders, nudges, and messages that just need to be delivered as-is. This is the DEFAULT for reminders.
- mode="agent" — Routes through the full agent pipeline via /agent_response. Use when the task needs to query live data, call tools, or perform analysis at execution time.

Examples of when to use each mode:
- "Remind me to check on my referral bonus" → notify (just deliver the message)
- "Remind me to water the garden" → notify
- "Every morning tell me today's monorail hours" → agent (needs to look up live data)
- "Check the garden stats every Sunday" → agent (needs to query the garden database)

For notify mode: Write the notification message as the user should see it, in second person. Not "remind me to...", but "Time to check on your referral bonus!" or "Don't forget to water the garden!"

Supported schedule types:
- cron: Produce a standard 5-field cron expression (min hour day month weekday). Example: "30 19 * * 2".
- interval: Provide interval_seconds as an integer (e.g., 900 for every 15 minutes).
- date: Provide run_at as an ISO-8601 timestamp. Timezone may be omitted and app defaults will apply (e.g., "2025-09-01T09:00:00").

Listing and deletion:
- Use list_scheduled_tasks to show existing tasks by their human-friendly names.
- To delete a task, ask the user for the task name and call delete_scheduled_task(name). If multiple tasks share a similar name, ask for clarification.

Clarifying questions:
- If any required detail (date, time, or recurrence pattern) is missing or ambiguous, ask a brief, direct clarifying question. Continue asking follow-ups until you have what you need.

Tool usage and responses:
- Use schedule_task to create the schedule.
- Use list_scheduled_tasks to display current schedules.
- Use delete_scheduled_task to remove a schedule by name.
- After a successful tool call (success=true), reply with a concise confirmation of what was scheduled and when it will run. Do not include any task_id.
  Examples:
  - "Scheduled for Sep 1 at 9:00 AM."
  - "Scheduled every 15 minutes."
  - "Scheduled every Tuesday at 7:30 PM."
- If the tool returns an error (success=false), briefly state the error message and do not attempt recovery.

Important:
- Default to mode="notify" for simple reminders and messages.
- Use mode="agent" only when live data or tool calls are needed at execution time.
- If the user's instruction is immediately schedulable, schedule directly without unnecessary questions.
""",
        tools=[schedule_task, list_scheduled_tasks, delete_scheduled_task],
        model=agent_model,
    )

    logger.debug(
        f"Scheduler agent created with model '{agent_model}' and the add_scheduled_task tool"
    )
    return scheduler
