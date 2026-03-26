"""
Tests for the logger service (CSV operations).
"""

import csv
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import pytz

from app.agents.logger.logger_service import log_action, query_action_log


@pytest.fixture
def csv_path(tmp_path):
    """Provide a temporary CSV path and patch the config."""
    path = tmp_path / "action_log.csv"
    with patch(
        "app.agents.logger.logger_service.config",
        **{"action_log_path": str(path)},
    ):
        yield path


class TestLogAction:
    def test_creates_csv_with_headers(self, csv_path):
        log_action("medication", 47.6, -122.3)

        with open(csv_path) as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == ["timestamp", "action", "latitude", "longitude"]

    def test_appends_rows(self, csv_path):
        log_action("medication", 47.6, -122.3)
        log_action("fed dog", 47.6, -122.3)

        with open(csv_path) as f:
            reader = csv.reader(f)
            next(reader)  # skip headers
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0][1] == "medication"
            assert rows[1][1] == "fed dog"

    def test_without_location(self, csv_path):
        result = log_action("meditation", None, None)

        with open(csv_path) as f:
            reader = csv.reader(f)
            next(reader)  # skip headers
            row = next(reader)
            assert row[2] == ""
            assert row[3] == ""

        assert "unavailable" in result

    def test_with_location(self, csv_path):
        result = log_action("medication", 47.6062, -122.3321)

        assert "47.6062" in result
        assert "-122.3321" in result

    def test_returns_confirmation(self, csv_path):
        result = log_action("medication", 47.6, -122.3)

        assert "Logged 'medication'" in result
        assert "location:" in result


class TestQueryActionLog:
    def _write_csv(self, csv_path, rows):
        """Helper to write test CSV data."""
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "action", "latitude", "longitude"])
            for row in rows:
                writer.writerow(row)

    def test_no_file(self, csv_path):
        result = query_action_log()
        assert "No action log entries found" in result

    def test_empty_csv(self, csv_path):
        self._write_csv(csv_path, [])
        result = query_action_log()
        assert "No action log entries found" in result

    def test_filters_by_action(self, csv_path):
        now = datetime.now(pytz.timezone("America/Los_Angeles")).isoformat()
        self._write_csv(
            csv_path,
            [
                [now, "medication", "47.6", "-122.3"],
                [now, "fed dog", "47.6", "-122.3"],
                [now, "medication", "47.6", "-122.3"],
            ],
        )
        result = query_action_log(action="medication")
        assert "2 entries" in result

    def test_filters_by_action_case_insensitive(self, csv_path):
        now = datetime.now(pytz.timezone("America/Los_Angeles")).isoformat()
        self._write_csv(
            csv_path,
            [
                [now, "Medication", "47.6", "-122.3"],
            ],
        )
        result = query_action_log(action="medication")
        assert "1 entries" in result

    def test_filters_by_days(self, csv_path):
        tz = pytz.timezone("America/Los_Angeles")
        recent = datetime.now(tz).isoformat()
        old = (datetime.now(tz) - timedelta(days=10)).isoformat()
        self._write_csv(
            csv_path,
            [
                [old, "medication", "47.6", "-122.3"],
                [recent, "medication", "47.6", "-122.3"],
            ],
        )
        result = query_action_log(days=7)
        assert "1 entries" in result

    def test_no_matching_results(self, csv_path):
        now = datetime.now(pytz.timezone("America/Los_Angeles")).isoformat()
        self._write_csv(
            csv_path,
            [
                [now, "medication", "47.6", "-122.3"],
            ],
        )
        result = query_action_log(action="nonexistent")
        assert "No entries found" in result
