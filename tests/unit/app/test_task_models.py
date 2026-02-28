"""
Tests for Pydantic validation in app.models.tasks — TaskSchedule,
TaskConfig, and TaskResultsStorage.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models.tasks import (
    APICallConfig,
    NotificationConfig,
    TaskConfig,
    TaskExecutionResult,
    TaskResultsStorage,
    TaskSchedule,
)

pytestmark = [pytest.mark.unit, pytest.mark.app]


# ===========================================================================
# TaskSchedule validation
# ===========================================================================


class TestTaskScheduleValidation:
    # --- cron ---------------------------------------------------------------

    def test_cron_requires_expression(self):
        """Cron schedule without expression raises ValidationError."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(type="cron")

    def test_cron_valid(self):
        """Cron schedule with expression is accepted."""
        s = TaskSchedule(type="cron", expression="0 7 * * *")
        assert s.type == "cron"
        assert s.expression == "0 7 * * *"

    def test_cron_rejects_interval_seconds(self):
        """Cron schedule cannot have interval_seconds."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(type="cron", expression="0 7 * * *", interval_seconds=60)

    def test_cron_rejects_run_at(self):
        """Cron schedule cannot have run_at."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(
                type="cron",
                expression="0 7 * * *",
                run_at=datetime(2030, 1, 1),
            )

    # --- interval -----------------------------------------------------------

    def test_interval_requires_interval_seconds(self):
        """Interval schedule without interval_seconds raises error."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(type="interval")

    def test_interval_valid(self):
        """Interval schedule with valid seconds is accepted."""
        s = TaskSchedule(type="interval", interval_seconds=300)
        assert s.interval_seconds == 300

    def test_interval_rejects_expression(self):
        """Interval schedule cannot have cron expression."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(
                type="interval",
                interval_seconds=60,
                expression="0 7 * * *",
            )

    def test_interval_rejects_run_at(self):
        """Interval schedule cannot have run_at."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(
                type="interval",
                interval_seconds=60,
                run_at=datetime(2030, 1, 1),
            )

    def test_interval_seconds_zero_raises(self):
        """interval_seconds=0 is rejected (ge=1)."""
        with pytest.raises(ValidationError):
            TaskSchedule(type="interval", interval_seconds=0)

    def test_interval_seconds_negative_raises(self):
        """Negative interval_seconds is rejected (ge=1)."""
        with pytest.raises(ValidationError):
            TaskSchedule(type="interval", interval_seconds=-10)

    def test_interval_seconds_minimum(self):
        """interval_seconds=1 is the minimum valid value."""
        s = TaskSchedule(type="interval", interval_seconds=1)
        assert s.interval_seconds == 1

    # --- date ---------------------------------------------------------------

    def test_date_requires_run_at(self):
        """Date schedule without run_at raises error."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(type="date")

    def test_date_valid(self):
        """Date schedule with run_at is accepted."""
        dt = datetime(2030, 6, 15, 10, 0)
        s = TaskSchedule(type="date", run_at=dt)
        assert s.run_at == dt

    def test_date_rejects_expression(self):
        """Date schedule cannot have cron expression."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(
                type="date",
                run_at=datetime(2030, 1, 1),
                expression="0 7 * * *",
            )

    def test_date_rejects_interval_seconds(self):
        """Date schedule cannot have interval_seconds."""
        with pytest.raises((ValidationError, ValueError)):
            TaskSchedule(
                type="date",
                run_at=datetime(2030, 1, 1),
                interval_seconds=60,
            )

    # --- invalid type -------------------------------------------------------

    def test_invalid_type_rejected(self):
        """A schedule type outside of the Literal set is rejected."""
        with pytest.raises(ValidationError):
            TaskSchedule(type="weekly", expression="something")


# ===========================================================================
# TaskConfig validation
# ===========================================================================


class TestTaskConfigValidation:
    def test_api_call_type_requires_api_call_field(self):
        """TaskConfig with type='api_call' but no api_call raises error."""
        with pytest.raises((ValidationError, ValueError)):
            TaskConfig(
                id="t1",
                name="Test",
                type="api_call",
                schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
                api_call=None,
            )

    def test_api_call_type_with_config_valid(self):
        """TaskConfig with all required fields is valid."""
        tc = TaskConfig(
            id="t1",
            name="Test",
            type="api_call",
            schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            api_call=APICallConfig(
                endpoint="/agent_response",
                method="POST",
                payload={"input": "hello"},
            ),
        )
        assert tc.id == "t1"
        assert tc.enabled is True  # default
        assert tc.max_retries == 3  # default

    def test_invalid_task_type_rejected(self):
        """A type outside of the Literal set is rejected."""
        with pytest.raises(ValidationError):
            TaskConfig(
                id="t1",
                name="Test",
                type="custom_function",
                schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            )

    def test_defaults_applied(self):
        """Default values for max_retries, retry_delay, enabled are set."""
        tc = TaskConfig(
            id="t1",
            name="Test",
            type="api_call",
            schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            api_call=APICallConfig(
                endpoint="/agent_response",
                method="POST",
                payload={},
            ),
        )
        assert tc.enabled is True
        assert tc.max_retries == 3
        assert tc.retry_delay == 60

    def test_mode_defaults_to_agent(self):
        """mode defaults to 'agent' when not specified."""
        tc = TaskConfig(
            id="t1",
            name="Test",
            type="api_call",
            schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            api_call=APICallConfig(
                endpoint="/agent_response",
                method="POST",
                payload={},
            ),
        )
        assert tc.mode == "agent"

    def test_notify_mode_requires_notification(self):
        """mode='notify' without notification raises error."""
        with pytest.raises((ValidationError, ValueError)):
            TaskConfig(
                id="t1",
                name="Test",
                type="api_call",
                mode="notify",
                schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            )

    def test_agent_mode_requires_api_call(self):
        """mode='agent' with type='api_call' but no api_call raises error."""
        with pytest.raises((ValidationError, ValueError)):
            TaskConfig(
                id="t1",
                name="Test",
                type="api_call",
                mode="agent",
                schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
                api_call=None,
            )

    def test_invalid_mode_rejected(self):
        """An invalid mode value is rejected."""
        with pytest.raises(ValidationError):
            TaskConfig(
                id="t1",
                name="Test",
                type="api_call",
                mode="unknown",
                schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
            )

    def test_notify_mode_with_notification_valid(self):
        """mode='notify' with notification config is valid."""
        tc = TaskConfig(
            id="t1",
            name="Reminder",
            type="api_call",
            mode="notify",
            schedule=TaskSchedule(type="cron", expression="0 9 * * *"),
            notification=NotificationConfig(message="Time to check your bonus!"),
        )
        assert tc.mode == "notify"
        assert tc.notification.message == "Time to check your bonus!"
        assert tc.notification.parse_mode == "HTML"
        assert tc.api_call is None

    def test_notification_empty_message_rejected(self):
        """NotificationConfig with empty message is rejected."""
        with pytest.raises(ValidationError):
            NotificationConfig(message="")


# ===========================================================================
# TaskResultsStorage validation
# ===========================================================================


class TestTaskResultsStorage:
    def _make_result(self, task_id="t1", execution_id="e1") -> TaskExecutionResult:
        return TaskExecutionResult(
            task_id=task_id,
            execution_id=execution_id,
            started_at=datetime(2026, 1, 1, 12, 0),
            success=True,
        )

    def test_add_result(self):
        """add_result appends a result."""
        storage = TaskResultsStorage()
        storage.add_result(self._make_result())
        assert len(storage.results) == 1

    def test_add_result_respects_max_results(self):
        """When exceeding max_results, oldest entries are dropped."""
        storage = TaskResultsStorage(max_results=3)

        for i in range(5):
            storage.add_result(self._make_result(execution_id=f"e{i}"))

        assert len(storage.results) == 3
        # The last 3 should remain
        ids = [r.execution_id for r in storage.results]
        assert ids == ["e2", "e3", "e4"]

    def test_get_results_for_task(self):
        """get_results_for_task filters by task_id and respects limit."""
        storage = TaskResultsStorage()
        for i in range(5):
            storage.add_result(self._make_result(task_id="a", execution_id=f"a{i}"))
        storage.add_result(self._make_result(task_id="b", execution_id="b0"))

        results = storage.get_results_for_task("a", limit=3)
        assert len(results) == 3
        assert all(r.task_id == "a" for r in results)

    def test_get_results_for_task_empty(self):
        """get_results_for_task returns empty list when no matches."""
        storage = TaskResultsStorage()
        results = storage.get_results_for_task("nonexistent")
        assert results == []

    def test_default_max_results(self):
        """Default max_results is 1000."""
        storage = TaskResultsStorage()
        assert storage.max_results == 1000
