"""
Tests that scheduled tasks capture the conversation that created them.
"""

import json

import pytest
from unittest.mock import patch, MagicMock
from agents import RunContextWrapper

from app.agents.scheduler_agent import schedule_task
from app.core import conversation_context

pytestmark = [pytest.mark.unit, pytest.mark.app]


async def _invoke(**kwargs) -> dict:
    """Invoke the schedule_task tool and return the task dict passed to storage."""
    captured = {}

    def fake_append(task):
        captured["task"] = task
        return "task-id"

    ctx = RunContextWrapper(context=None)
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
