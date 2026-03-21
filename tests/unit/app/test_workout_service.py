"""Tests for the workout service."""

import pytest
from unittest.mock import patch, AsyncMock

from app.core.settings import Config
from app.agents.workout.workout_service import (
    format_workout_markdown,
    add_notes,
    get_workout_summary,
    fetch_latest_workout,
    fetch_workout_by_date,
)


SAMPLE_ACTIVITY = {
    "id": 12345678,
    "name": "Morning Run",
    "type": "Run",
    "distance": 9978.1,  # ~6.2 miles
    "moving_time": 3134,  # ~52:14
    "elapsed_time": 3300,
    "total_elevation_gain": 64.0,  # ~210 ft
    "average_heartrate": 148.0,
    "max_heartrate": 165.0,
    "start_date": "2026-03-19T14:30:00Z",
    "start_date_local": "2026-03-19T07:30:00",
    "splits_standard": [
        {
            "distance": 1609.34,
            "moving_time": 525,
            "average_heartrate": 138.0,
            "elevation_difference": 5.0,
        },
        {
            "distance": 1609.34,
            "moving_time": 510,
            "average_heartrate": 145.0,
            "elevation_difference": 3.0,
        },
        {
            "distance": 1609.34,
            "moving_time": 505,
            "average_heartrate": 150.0,
            "elevation_difference": -2.0,
        },
        {
            "distance": 1609.34,
            "moving_time": 498,
            "average_heartrate": 152.0,
            "elevation_difference": 4.0,
        },
        {
            "distance": 1609.34,
            "moving_time": 512,
            "average_heartrate": 149.0,
            "elevation_difference": 1.0,
        },
        {
            "distance": 1609.34,
            "moving_time": 490,
            "average_heartrate": 155.0,
            "elevation_difference": -3.0,
        },
        {
            "distance": 321.8,
            "moving_time": 94,
            "average_heartrate": 158.0,
            "elevation_difference": 0.0,
        },
    ],
}


@pytest.fixture()
def test_config(tmp_path):
    return Config.create_test_config(storage_path=str(tmp_path))


class TestFormatWorkoutMarkdown:
    def test_basic_formatting(self):
        """Test that markdown output has expected structure."""
        result = format_workout_markdown(SAMPLE_ACTIVITY)

        assert "# Run — March 19, 2026" in result
        assert "## Summary" in result
        assert "6.2 mi" in result
        assert "Avg HR: 148 bpm" in result
        assert "Max HR: 165 bpm" in result
        assert "Elevation Gain:" in result
        assert "## Splits" in result
        assert "| Mile | Pace | HR |" in result

    def test_splits_count(self):
        """Test that all splits are included."""
        result = format_workout_markdown(SAMPLE_ACTIVITY)
        # 7 splits in sample data
        lines = [
            line
            for line in result.splitlines()
            if line.startswith("| ")
            and not line.startswith("| Mile")
            and not line.startswith("|--")
        ]
        assert len(lines) == 7

    def test_no_heartrate(self):
        """Test formatting when heartrate data is missing."""
        activity = {**SAMPLE_ACTIVITY, "average_heartrate": None, "max_heartrate": None}
        result = format_workout_markdown(activity)

        assert "Avg HR" not in result
        assert "Max HR" not in result

    def test_no_splits(self):
        """Test formatting when splits data is missing."""
        activity = {**SAMPLE_ACTIVITY, "splits_standard": []}
        result = format_workout_markdown(activity)

        assert "## Splits" not in result


class TestAddNotes:
    def test_add_notes_creates_section(self, test_config, tmp_path):
        """Test adding notes to a file without a Notes section."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19-12345678.md"
        workout_file.write_text(
            "# Run — March 19, 2026\n\n## Summary\n- Distance: 6.2 mi\n"
        )

        with patch("app.agents.workout.workout_service.config", test_config):
            result = add_notes("2026-03-19", "Felt great\nHad a gel at mile 4")

        assert "Notes added" in result
        content = workout_file.read_text()
        assert "## Notes" in content
        assert "- Felt great" in content
        assert "- Had a gel at mile 4" in content

    def test_add_notes_appends_to_existing(self, test_config, tmp_path):
        """Test appending notes to a file with existing Notes section."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19-12345678.md"
        workout_file.write_text("# Run\n\n## Notes\n- First note\n")

        with patch("app.agents.workout.workout_service.config", test_config):
            result = add_notes("2026-03-19", "Second note")

        assert "Notes added" in result
        content = workout_file.read_text()
        assert "- First note" in content
        assert "- Second note" in content

    def test_add_notes_no_file(self, test_config):
        """Test adding notes when no workout file exists."""
        with patch("app.agents.workout.workout_service.config", test_config):
            result = add_notes("2026-03-19", "Some notes")

        assert "No workout file found" in result


class TestGetWorkoutSummary:
    def test_get_summary(self, test_config, tmp_path):
        """Test reading a workout file."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        content = "# Run — March 19, 2026\n\n## Summary\n- Distance: 6.2 mi\n"
        (workout_dir / "2026-03-19-12345678.md").write_text(content)

        with patch("app.agents.workout.workout_service.config", test_config):
            result = get_workout_summary("2026-03-19")

        assert result == content

    def test_get_summary_not_found(self, test_config):
        """Test reading a non-existent workout file."""
        with patch("app.agents.workout.workout_service.config", test_config):
            result = get_workout_summary("2026-03-19")

        assert "No workout file found" in result


class TestFetchLatestWorkout:
    @pytest.mark.asyncio
    async def test_fetch_latest_workout(self, test_config, tmp_path):
        """Test fetching and saving the latest workout."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.get_latest_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_ACTIVITY,
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_latest_workout()

        assert "6.2 mi" in result
        assert "Saved workout" in result

        # Verify file was created
        workout_dir = tmp_path / "workouts"
        files = list(workout_dir.glob("*.md"))
        assert len(files) == 1
        assert "2026-03-19" in files[0].name


class TestFetchWorkoutByDate:
    @pytest.mark.asyncio
    async def test_fetch_workout_by_date(self, test_config, tmp_path):
        """Test fetching a workout by date."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.get_activities_on_date",
                new_callable=AsyncMock,
                return_value=SAMPLE_ACTIVITY,
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19")

        assert "Saved workout" in result

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_not_found(self, test_config):
        """Test fetching a workout when none exists for the date."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.get_activities_on_date",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19")

        assert "No run found" in result
