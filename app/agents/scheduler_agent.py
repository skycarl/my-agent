"""
Scheduler agent for converting natural-language scheduling requests into tasks.

This agent uses the add_scheduled_task tool to create scheduled API calls
to the application's /agent_response endpoint.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
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
        handoff_description="Converts natural-language scheduling requests into scheduled tasks (cron, interval, or one-time). Also lists and deletes existing schedules.",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are the Scheduler. You convert natural-language instructions into scheduled tasks using the schedule_task tool.

Execution modes:
- mode="notify" (DEFAULT) — Sends a Telegram message directly. Use for simple reminders and nudges.
- mode="agent" — Routes through the agent pipeline. Use when the task needs live data or tool calls at execution time.

Mode examples:
- "Remind me to check on my referral bonus" → notify
- "Every morning tell me today's monorail hours" → agent (needs live data)

For notify mode: Write the message in second person as the user should see it (e.g., "Time to check on your referral bonus!").

Schedule types:
- cron: 5-field expression (e.g., "30 19 * * 2")
- interval: interval_seconds as integer (e.g., 900 for 15 min)
- date: ISO-8601 timestamp (e.g., "2025-09-01T09:00:00")

Listing and deletion:
- list_scheduled_tasks to show existing tasks.
- delete_scheduled_task(name) to remove one. If ambiguous, ask for clarification.

After a successful schedule, reply with a concise confirmation (e.g., "Scheduled every Tuesday at 7:30 PM."). On error, state the error briefly.

If any required detail is missing, ask a brief clarifying question. If immediately schedulable, schedule directly.

Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[schedule_task, list_scheduled_tasks, delete_scheduled_task],
        model=agent_model,
    )

    logger.debug(
        f"Scheduler agent created with model '{agent_model}' and the add_scheduled_task tool"
    )
    return scheduler
