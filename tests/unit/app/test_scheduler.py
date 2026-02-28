"""
Tests for app.core.scheduler — SchedulerService scheduling logic,
configuration loading, and reload behaviour.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.settings import Config
from app.models.tasks import APICallConfig, TaskConfig, TaskSchedule

pytestmark = [pytest.mark.unit, pytest.mark.app]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config(tmp_path, monkeypatch):
    """Isolated Config pointing at a temp storage directory."""
    cfg = Config.create_test_config(
        storage_path=str(tmp_path),
        scheduler_timezone="America/Los_Angeles",
        scheduler_enabled=True,
    )
    monkeypatch.setattr("app.core.scheduler.config", cfg)
    return cfg


@pytest.fixture()
def scheduler_service(test_config):
    """Create a fresh SchedulerService with a mocked APScheduler."""
    from app.core.scheduler import SchedulerService

    svc = SchedulerService()
    # Replace the real APScheduler with a mock to avoid event loop issues
    svc.scheduler = MagicMock()
    svc.scheduler.get_jobs.return_value = []
    return svc


@pytest.fixture()
def tasks_file(test_config):
    """Path to the tasks config file."""
    return Path(test_config.tasks_config_path)


def _make_task_config(
    task_id="t1",
    name="Test",
    schedule_type="cron",
    expression="0 7 * * *",
    interval_seconds=None,
    run_at=None,
    enabled=True,
) -> TaskConfig:
    """Build a minimal TaskConfig for scheduling tests."""
    schedule_kwargs = {"type": schedule_type}
    if expression is not None:
        schedule_kwargs["expression"] = expression
    if interval_seconds is not None:
        schedule_kwargs["interval_seconds"] = interval_seconds
    if run_at is not None:
        schedule_kwargs["run_at"] = run_at

    return TaskConfig(
        id=task_id,
        name=name,
        type="api_call",
        enabled=enabled,
        schedule=TaskSchedule(**schedule_kwargs),
        api_call=APICallConfig(
            endpoint="/agent_response",
            method="POST",
            payload={"input": "test"},
            timeout=120,
        ),
    )


def _write_config(tasks_file: Path, tasks: list[dict], version="1.0"):
    """Write a tasks configuration JSON to the specified path."""
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    tasks_file.write_text(
        json.dumps({"version": version, "tasks": tasks}, indent=2),
        encoding="utf-8",
    )


# ===========================================================================
# _schedule_task tests
# ===========================================================================


class TestScheduleTask:
    def test_valid_cron_creates_job(self, scheduler_service):
        """A valid cron task calls scheduler.add_job and returns True."""
        task = _make_task_config(expression="0 7 * * *")
        result = scheduler_service._schedule_task(task)

        assert result is True
        scheduler_service.scheduler.add_job.assert_called_once()
        assert task.id in scheduler_service.loaded_task_ids

    def test_invalid_cron_expression(self, scheduler_service):
        """An invalid cron expression (fails croniter validation) returns False."""
        task = _make_task_config(expression="99 99 99 99 99")
        result = scheduler_service._schedule_task(task)

        assert result is False
        scheduler_service.scheduler.add_job.assert_not_called()

    def test_wrong_field_count_cron(self, scheduler_service):
        """A cron expression with != 5 fields returns False."""
        task = _make_task_config(expression="0 7 * *")  # only 4 fields
        result = scheduler_service._schedule_task(task)

        assert result is False
        scheduler_service.scheduler.add_job.assert_not_called()

    def test_six_field_cron_rejected(self, scheduler_service):
        """A 6-field cron expression is rejected (only 5 allowed)."""
        task = _make_task_config(expression="0 0 7 * * *")
        result = scheduler_service._schedule_task(task)

        assert result is False

    def test_disabled_task_returns_false(self, scheduler_service):
        """A disabled task is skipped."""
        task = _make_task_config(enabled=False)
        result = scheduler_service._schedule_task(task)

        assert result is False
        scheduler_service.scheduler.add_job.assert_not_called()

    def test_valid_interval_creates_job(self, scheduler_service):
        """A valid interval task calls add_job and returns True."""
        task = _make_task_config(
            schedule_type="interval",
            expression=None,
            interval_seconds=300,
        )
        result = scheduler_service._schedule_task(task)

        assert result is True
        scheduler_service.scheduler.add_job.assert_called_once()

    def test_valid_date_creates_job(self, scheduler_service):
        """A valid date task calls add_job and returns True."""
        from datetime import datetime

        import pytz

        tz = pytz.timezone("America/Los_Angeles")
        run_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=tz)

        task = _make_task_config(
            schedule_type="date",
            expression=None,
            run_at=run_at,
        )
        result = scheduler_service._schedule_task(task)

        assert result is True
        scheduler_service.scheduler.add_job.assert_called_once()

    def test_cron_missing_expression(self, scheduler_service):
        """A cron task without an expression returns False."""
        # We need to bypass pydantic validation so manually set expression to None
        task = _make_task_config(expression="0 7 * * *")
        task.schedule.expression = None
        result = scheduler_service._schedule_task(task)

        assert result is False

    def test_interval_missing_seconds(self, scheduler_service):
        """An interval task without interval_seconds returns False."""
        task = _make_task_config(
            schedule_type="interval",
            expression=None,
            interval_seconds=60,
        )
        task.schedule.interval_seconds = None
        result = scheduler_service._schedule_task(task)

        assert result is False

    def test_date_missing_run_at(self, scheduler_service):
        """A date task without run_at returns False."""
        from datetime import datetime

        import pytz

        tz = pytz.timezone("America/Los_Angeles")
        run_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=tz)

        task = _make_task_config(
            schedule_type="date",
            expression=None,
            run_at=run_at,
        )
        task.schedule.run_at = None
        result = scheduler_service._schedule_task(task)

        assert result is False


# ===========================================================================
# _load_tasks_configuration tests
# ===========================================================================


class TestLoadTasksConfiguration:
    def test_missing_file_returns_empty(self, scheduler_service, tasks_file):
        """If the config file does not exist, return an empty TasksConfiguration."""
        assert not tasks_file.exists()
        result = scheduler_service._load_tasks_configuration()

        assert result is not None
        assert result.tasks == []

    def test_valid_json_returns_configuration(self, scheduler_service, tasks_file):
        """A valid JSON file is loaded into a TasksConfiguration."""
        _write_config(
            tasks_file,
            [
                {
                    "id": "t1",
                    "name": "Test",
                    "type": "api_call",
                    "enabled": True,
                    "schedule": {"type": "cron", "expression": "0 7 * * *"},
                    "api_call": {
                        "endpoint": "/agent_response",
                        "method": "POST",
                        "payload": {"input": "hi"},
                        "timeout": 120,
                    },
                }
            ],
        )
        result = scheduler_service._load_tasks_configuration()

        assert result is not None
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "t1"

    def test_invalid_json_returns_none(self, scheduler_service, tasks_file):
        """Corrupted JSON returns None."""
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text("{invalid json!!!", encoding="utf-8")

        result = scheduler_service._load_tasks_configuration()
        assert result is None

    def test_invalid_schema_returns_none(self, scheduler_service, tasks_file):
        """Valid JSON but invalid schema (e.g. bad schedule type) returns None."""
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "tasks": [
                        {
                            "id": "bad",
                            "name": "Bad",
                            "type": "api_call",
                            "schedule": {"type": "unknown_type"},
                            "api_call": {
                                "endpoint": "/agent_response",
                                "method": "POST",
                                "payload": {},
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = scheduler_service._load_tasks_configuration()
        assert result is None


# ===========================================================================
# reload_configuration tests
# ===========================================================================


class TestReloadConfiguration:
    def test_reload_clears_and_reschedules(self, scheduler_service, tasks_file):
        """reload_configuration clears existing jobs and schedules new ones."""
        # Seed a task on disk
        _write_config(
            tasks_file,
            [
                {
                    "id": "t1",
                    "name": "Test",
                    "type": "api_call",
                    "enabled": True,
                    "schedule": {"type": "cron", "expression": "0 7 * * *"},
                    "api_call": {
                        "endpoint": "/agent_response",
                        "method": "POST",
                        "payload": {"input": "test"},
                        "timeout": 120,
                    },
                }
            ],
        )

        # Pre-populate loaded_task_ids to verify they are cleared
        scheduler_service.loaded_task_ids = {"old-id"}
        scheduler_service.scheduler.get_job.return_value = MagicMock()

        result = scheduler_service.reload_configuration()

        assert result is True
        # Old jobs should have been cleared
        assert "old-id" not in scheduler_service.loaded_task_ids
        # New task should have been scheduled
        assert "t1" in scheduler_service.loaded_task_ids
        scheduler_service.scheduler.add_job.assert_called_once()

    def test_reload_returns_false_on_bad_config(self, scheduler_service, tasks_file):
        """reload_configuration returns False when config cannot be loaded."""
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text("not json", encoding="utf-8")

        result = scheduler_service.reload_configuration()
        assert result is False

    def test_reload_with_empty_file(self, scheduler_service, tasks_file):
        """Reloading with no tasks schedules zero jobs."""
        _write_config(tasks_file, [])

        result = scheduler_service.reload_configuration()
        assert result is True
        assert len(scheduler_service.loaded_task_ids) == 0

    def test_reload_updates_hash(self, scheduler_service, tasks_file):
        """After reload, the config_file_hash is updated."""
        _write_config(tasks_file, [])

        scheduler_service.reload_configuration()
        assert scheduler_service.config_file_hash is not None
