"""
Tests for app.core.task_store — append, list, and delete helpers for
the scheduled_tasks.json configuration file.
"""

import json

import pytest

from app.core.settings import Config
from app.core.task_store import (
    append_task_to_config,
    delete_task_by_id,
    list_tasks_from_config,
)

pytestmark = [pytest.mark.unit, pytest.mark.app]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config(tmp_path, monkeypatch):
    """Create an isolated Config that writes to a temp directory."""
    cfg = Config.create_test_config(storage_path=str(tmp_path))
    # Patch the global ``config`` object used inside task_store
    monkeypatch.setattr("app.core.task_store.config", cfg)
    return cfg


@pytest.fixture()
def tasks_file(test_config):
    """Return the Path to the tasks config file used by the test config."""
    from pathlib import Path

    return Path(test_config.tasks_config_path)


# ---------------------------------------------------------------------------
# Helper to build a minimal task dict
# ---------------------------------------------------------------------------


def _make_task(
    name="test-task",
    schedule_type="cron",
    expression="0 7 * * *",
    interval_seconds=None,
    run_at=None,
    enabled=True,
    task_id=None,
):
    schedule = {"type": schedule_type}
    if expression is not None:
        schedule["expression"] = expression
    if interval_seconds is not None:
        schedule["interval_seconds"] = interval_seconds
    if run_at is not None:
        schedule["run_at"] = run_at

    task = {
        "name": name,
        "type": "api_call",
        "enabled": enabled,
        "schedule": schedule,
        "api_call": {
            "endpoint": "/agent_response",
            "method": "POST",
            "payload": {"input": "hello"},
            "timeout": 120,
        },
    }
    if task_id is not None:
        task["id"] = task_id
    return task


# ===========================================================================
# append_task_to_config tests
# ===========================================================================


class TestAppendTask:
    def test_happy_path_cron(self, test_config, tasks_file):
        """Appending a cron task writes a valid JSON file and returns an id."""
        task = _make_task(schedule_type="cron", expression="30 19 * * 2")
        task_id = append_task_to_config(task)

        assert task_id  # non-empty string
        data = json.loads(tasks_file.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == task_id
        assert data["tasks"][0]["schedule"]["type"] == "cron"

    def test_happy_path_interval(self, test_config, tasks_file):
        """Appending an interval task stores interval_seconds correctly."""
        task = _make_task(
            schedule_type="interval",
            expression=None,
            interval_seconds=900,
        )
        task_id = append_task_to_config(task)

        data = json.loads(tasks_file.read_text())
        stored = data["tasks"][0]
        assert stored["id"] == task_id
        assert stored["schedule"]["interval_seconds"] == 900

    def test_happy_path_date(self, test_config, tasks_file):
        """Appending a date task normalizes run_at to ISO-8601."""
        task = _make_task(
            schedule_type="date",
            expression=None,
            run_at="2026-09-01T09:00:00",
        )
        task_id = append_task_to_config(task)

        data = json.loads(tasks_file.read_text())
        stored = data["tasks"][0]
        assert stored["id"] == task_id
        # run_at should have been parsed and serialized back
        assert "2026-09-01" in stored["schedule"]["run_at"]

    def test_auto_generates_uuid(self, test_config):
        """When no id is provided, append generates one."""
        task = _make_task()
        assert "id" not in task or task.get("id") is None
        task_id = append_task_to_config(task)
        assert isinstance(task_id, str)
        assert len(task_id) == 32  # hex uuid4

    def test_explicit_id_preserved(self, test_config, tasks_file):
        """An explicitly provided id is preserved."""
        task = _make_task(task_id="my-custom-id")
        task_id = append_task_to_config(task)
        assert task_id == "my-custom-id"
        data = json.loads(tasks_file.read_text())
        assert data["tasks"][0]["id"] == "my-custom-id"

    def test_creates_file_if_missing(self, test_config, tasks_file):
        """If the config file does not exist it is created."""
        assert not tasks_file.exists()
        append_task_to_config(_make_task())
        assert tasks_file.exists()

    def test_preserves_existing_tasks(self, test_config, tasks_file):
        """Appending a second task does not overwrite the first."""
        append_task_to_config(_make_task(name="first"))
        append_task_to_config(_make_task(name="second"))

        data = json.loads(tasks_file.read_text())
        names = [t["name"] for t in data["tasks"]]
        assert names == ["first", "second"]

    def test_last_modified_updated(self, test_config, tasks_file):
        """last_modified field is set after appending."""
        append_task_to_config(_make_task())
        data = json.loads(tasks_file.read_text())
        assert "last_modified" in data

    def test_handles_corrupted_json(self, test_config, tasks_file):
        """If existing file contains invalid JSON, start fresh with new tasks."""
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text("NOT VALID JSON", encoding="utf-8")

        task_id = append_task_to_config(_make_task())
        data = json.loads(tasks_file.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == task_id


# ===========================================================================
# list_tasks_from_config tests
# ===========================================================================


class TestListTasks:
    def test_list_empty(self, test_config):
        """Listing from an absent file returns an empty list."""
        tasks = list_tasks_from_config()
        assert tasks == []

    def test_list_all(self, test_config):
        """All tasks are listed by default."""
        append_task_to_config(_make_task(name="a"))
        append_task_to_config(_make_task(name="b"))
        tasks = list_tasks_from_config()
        assert len(tasks) == 2

    def test_filter_only_enabled(self, test_config):
        """only_enabled=True excludes disabled tasks."""
        append_task_to_config(_make_task(name="on", enabled=True))
        append_task_to_config(_make_task(name="off", enabled=False))

        enabled = list_tasks_from_config(only_enabled=True)
        assert len(enabled) == 1
        assert enabled[0]["name"] == "on"

    def test_filter_name_case_insensitive(self, test_config):
        """name_filter is case-insensitive substring match."""
        append_task_to_config(_make_task(name="Morning Run"))
        append_task_to_config(_make_task(name="Evening Walk"))

        results = list_tasks_from_config(name_filter="morning")
        assert len(results) == 1
        assert results[0]["name"] == "Morning Run"

    def test_filter_name_partial_match(self, test_config):
        """name_filter matches substrings."""
        append_task_to_config(_make_task(name="Daily Garden Check"))
        append_task_to_config(_make_task(name="Weekly Garden Report"))

        results = list_tasks_from_config(name_filter="Garden")
        assert len(results) == 2

    def test_combined_filters(self, test_config):
        """Combining only_enabled and name_filter narrows results."""
        append_task_to_config(_make_task(name="Daily Check", enabled=True))
        append_task_to_config(_make_task(name="Daily Report", enabled=False))
        append_task_to_config(_make_task(name="Weekly Check", enabled=True))

        results = list_tasks_from_config(only_enabled=True, name_filter="daily")
        assert len(results) == 1
        assert results[0]["name"] == "Daily Check"


# ===========================================================================
# delete_task_by_id tests
# ===========================================================================


class TestDeleteTask:
    def test_delete_existing(self, test_config, tasks_file):
        """Deleting an existing task returns True and removes it from file."""
        task_id = append_task_to_config(_make_task(name="to-delete"))
        assert delete_task_by_id(task_id) is True

        data = json.loads(tasks_file.read_text())
        assert len(data["tasks"]) == 0

    def test_delete_nonexistent(self, test_config):
        """Deleting a non-existent id returns False."""
        append_task_to_config(_make_task(name="keeper"))
        assert delete_task_by_id("no-such-id") is False

    def test_preserves_other_tasks(self, test_config, tasks_file):
        """Deleting one task leaves the others intact."""
        id1 = append_task_to_config(_make_task(name="first"))
        id2 = append_task_to_config(_make_task(name="second"))
        id3 = append_task_to_config(_make_task(name="third"))

        delete_task_by_id(id2)
        data = json.loads(tasks_file.read_text())
        remaining_ids = [t["id"] for t in data["tasks"]]
        assert id1 in remaining_ids
        assert id3 in remaining_ids
        assert id2 not in remaining_ids

    def test_delete_updates_last_modified(self, test_config, tasks_file):
        """Deletion updates last_modified."""
        task_id = append_task_to_config(_make_task())

        delete_task_by_id(task_id)
        data_after = json.loads(tasks_file.read_text())

        # last_modified should be present in both but the value may change
        assert "last_modified" in data_after

    def test_delete_from_empty_store(self, test_config):
        """Deleting from an empty / non-existent store returns False."""
        assert delete_task_by_id("anything") is False
