"""
Tests that scheduled tasks capture the conversation that created them.
"""

import json

import pytest
from unittest.mock import patch, MagicMock

from app.agents.scheduler_agent import schedule_task
from app.core import conversation_context
from tests.helpers import tool_context

pytestmark = [pytest.mark.unit, pytest.mark.app]


async def _invoke(**kwargs) -> dict:
    """Invoke the schedule_task tool and return the task dict passed to storage."""
    captured = {}

    def fake_append(task):
        captured["task"] = task
        return "task-id"

    ctx = tool_context()
    with (
        patch("app.core.task_store.append_task_to_config", side_effect=fake_append),
        patch("app.core.scheduler.scheduler_service", MagicMock()),
    ):
        await schedule_task.on_invoke_tool(ctx, json.dumps(kwargs))
    return captured["task"]


class TestSchedulerConversationCapture:
    @pytest.mark.asyncio
    async def test_notify_task_records_conversation_id(self):
        conversation_context.set_conversation_id("555")
        task = await _invoke(
            name="Reminder",
            schedule_type="date",
            run_at="2030-01-01T09:00:00",
            instruction="Time to test!",
            mode="notify",
        )
        assert task["conversation_id"] == "555"

    @pytest.mark.asyncio
    async def test_agent_task_injects_conversation_id_into_payload(self):
        conversation_context.set_conversation_id("-100999")
        task = await _invoke(
            name="Daily monorail",
            schedule_type="cron",
            cron_expression="30 7 * * *",
            instruction="What are tomorrow's monorail hours?",
            mode="agent",
        )
        assert task["conversation_id"] == "-100999"
        assert task["api_call"]["payload"]["conversation_id"] == "-100999"

    @pytest.mark.asyncio
    async def test_no_conversation_context_leaves_none(self):
        conversation_context.set_conversation_id(None)
        task = await _invoke(
            name="Reminder",
            schedule_type="date",
            run_at="2030-01-01T09:00:00",
            instruction="Time to test!",
            mode="notify",
        )
        assert task["conversation_id"] is None


class TestScheduleTaskInstructionValidation:
    @pytest.mark.asyncio
    async def test_agent_mode_rejects_blank_instruction(self):
        """An agent-mode task with a blank instruction is rejected, not stored."""
        captured = {}

        ctx = tool_context()
        with (
            patch(
                "app.core.task_store.append_task_to_config",
                side_effect=lambda t: captured.setdefault("task", t) or "task-id",
            ),
            patch("app.core.scheduler.scheduler_service", MagicMock()),
        ):
            result = await schedule_task.on_invoke_tool(
                ctx,
                json.dumps(
                    {
                        "name": "Broken",
                        "schedule_type": "cron",
                        "cron_expression": "0 9 * * *",
                        "instruction": "   ",
                        "mode": "agent",
                    }
                ),
            )

        assert "Error" in str(result)
        assert "task" not in captured
