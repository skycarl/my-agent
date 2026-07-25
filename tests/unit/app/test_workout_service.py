"""Tests for the workout service."""

from datetime import datetime

import pytest
import pytz
from unittest.mock import patch, AsyncMock

from app.core.settings import Config
from app.agents.workout.workout_service import (
    format_workout_markdown,
    update_section,
    get_workout_summary,
    fetch_latest_workout,
    fetch_workout_by_date,
    list_workouts_on_date,
    _slugify,
    _format_duration,
    _parse_date,
    _save_workout,
    _select_matching,
    _speed_to_pace,
    _celsius_to_fahrenheit,
)


SAMPLE_RUN_ACTIVITY = {
    "id": 12345678,
    "name": "Morning Run",
    "type": "Run",
    "sport_type": "Run",
    "description": "Felt strong on the back half.\nLegs a little heavy at the start.",
    "perceived_exertion": 6.0,
    "suffer_score": 88,
    "pr_count": 2,
    "achievement_count": 5,
    "distance": 9978.1,  # ~6.2 miles
    "moving_time": 3134,  # ~52:14
    "elapsed_time": 3300,
    "total_elevation_gain": 64.0,  # ~210 ft
    "average_speed": 3.18,  # m/s ~8:26/mi
    "max_speed": 4.2,
    "average_heartrate": 148.0,
    "max_heartrate": 165.0,
    "average_cadence": 88.0,  # Strava reports half-cadence for runs
    "average_watts": 278,
    "calories": 650,
    "average_temp": 8,  # Celsius
    "trainer": False,
    "device_name": "COROS PACE 3",
    "workout_type": 0,
    "elev_high": 85.0,
    "elev_low": 45.0,
    "gear": {"name": "Altra Torin 7"},
    "start_date": "2026-03-19T14:30:00Z",
    "start_date_local": "2026-03-19T07:30:00",
    "splits_standard": [
        {
            "distance": 1609.34,
            "moving_time": 525,
            "average_speed": 3.07,
            "average_heartrate": 138.0,
            "elevation_difference": 5.0,
            "average_grade_adjusted_speed": 3.05,
            "pace_zone": 1,
        },
        {
            "distance": 1609.34,
            "moving_time": 510,
            "average_speed": 3.16,
            "average_heartrate": 145.0,
            "elevation_difference": 3.0,
            "average_grade_adjusted_speed": 3.14,
            "pace_zone": 2,
        },
        {
            "distance": 321.8,
            "moving_time": 94,
            "average_speed": 3.42,
            "average_heartrate": 158.0,
            "elevation_difference": 0.0,
            "average_grade_adjusted_speed": 3.42,
            "pace_zone": 2,
        },
    ],
    "best_efforts": [
        {"name": "400m", "elapsed_time": 103, "distance": 400, "moving_time": 103},
        {
            "name": "1 mile",
            "elapsed_time": 498,
            "distance": 1609.34,
            "moving_time": 498,
        },
    ],
}

SAMPLE_RIDE_ACTIVITY = {
    "id": 87654321,
    "name": "Zwift Easy Spin",
    "type": "Ride",
    "sport_type": "VirtualRide",
    "distance": 24140.0,  # ~15 miles
    "moving_time": 2700,
    "elapsed_time": 2800,
    "total_elevation_gain": 30.0,
    "average_speed": 8.94,
    "max_speed": 12.5,
    "average_heartrate": 130.0,
    "max_heartrate": 145.0,
    "average_watts": 180,
    "max_watts": 320,
    "weighted_average_watts": 195,
    "average_cadence": 85,
    "kilojoules": 486,
    "calories": 520,
    "average_temp": 20,
    "trainer": True,
    "device_name": "Zwift",
    "workout_type": None,
    "start_date": "2026-03-20T22:00:00Z",
    "start_date_local": "2026-03-20T15:00:00",
}

SAMPLE_STRENGTH_ACTIVITY = {
    "id": 99999999,
    "name": "Gym Session",
    "type": "WeightTraining",
    "sport_type": "WeightTraining",
    "distance": 0,
    "moving_time": 3600,
    "elapsed_time": 4200,
    "total_elevation_gain": 0,
    "average_heartrate": 120.0,
    "max_heartrate": 155.0,
    "calories": 400,
    "start_date": "2026-03-21T17:00:00Z",
    "start_date_local": "2026-03-21T10:00:00",
}

SAMPLE_ZONES = [
    {
        "type": "heartrate",
        "distribution_buckets": [
            {"min": 0, "max": 135, "time": 600},
            {"min": 135, "max": 152, "time": 900},
            {"min": 152, "max": 161, "time": 1200},
            {"min": 161, "max": 171, "time": 300},
            {"min": 171, "max": -1, "time": 134},
        ],
    }
]

SAMPLE_LAPS = [
    {
        "name": "Warm Up",
        "distance": 3218.68,
        "moving_time": 1088,
        "average_speed": 2.96,
        "average_heartrate": 131.0,
        "max_heartrate": 142.0,
        "average_cadence": 84.0,
        "average_watts": 240,
        "total_elevation_gain": 12.0,
    },
    {
        "name": "Interval 1",
        "distance": 1609.34,
        "moving_time": 458,
        "average_speed": 3.51,
        "average_heartrate": 159.0,
        "max_heartrate": 164.0,
        "average_cadence": 90.0,
        "average_watts": 295,
        "total_elevation_gain": 3.0,
    },
    {
        "name": "Cool Down",
        "distance": 3218.68,
        "moving_time": 1095,
        "average_speed": 2.94,
        "average_heartrate": 150.0,
        "max_heartrate": 155.0,
        "average_cadence": 84.0,
        "average_watts": 238,
        "total_elevation_gain": 8.0,
    },
]


@pytest.fixture()
def test_config(tmp_path):
    return Config.create_test_config(storage_path=str(tmp_path))


class TestHelpers:
    def test_slugify(self):
        assert _slugify("Morning Run") == "morning-run"
        assert _slugify("Saturday Track – 6x1000m") == "saturday-track-6x1000m"
        assert _slugify("Zwift Easy Spin") == "zwift-easy-spin"

    def test_format_duration(self):
        assert _format_duration(3134) == "52:14"
        assert _format_duration(4867) == "1:21:07"
        assert _format_duration(65) == "1:05"

    def test_speed_to_pace(self):
        # 3.18 m/s should be roughly 8:26/mi
        pace = _speed_to_pace(3.18)
        assert pace.endswith("/mi")
        assert pace.startswith("8:")

    def test_celsius_to_fahrenheit(self):
        assert _celsius_to_fahrenheit(0) == 32
        assert _celsius_to_fahrenheit(100) == 212
        assert _celsius_to_fahrenheit(8) == 46


def _fixed_now(year: int, month: int, day: int):
    return pytz.timezone("America/Los_Angeles").localize(
        datetime(year, month, day, 12, 0)
    )


class TestParseDate:
    def test_month_day_past_uses_current_year(self):
        with patch(
            "app.agents.workout.workout_service.now_local",
            return_value=_fixed_now(2026, 7, 23),
        ):
            result = _parse_date("March 19")
        assert (result.year, result.month, result.day) == (2026, 3, 19)

    def test_month_day_future_assumes_previous_year(self):
        with patch(
            "app.agents.workout.workout_service.now_local",
            return_value=_fixed_now(2026, 1, 10),
        ):
            result = _parse_date("December 15")
        assert (result.year, result.month, result.day) == (2025, 12, 15)

    def test_february_29_parses_in_leap_year(self):
        with patch(
            "app.agents.workout.workout_service.now_local",
            return_value=_fixed_now(2024, 7, 1),
        ):
            result = _parse_date("February 29")
        assert (result.year, result.month, result.day) == (2024, 2, 29)

    def test_unparseable_raises(self):
        with patch(
            "app.agents.workout.workout_service.now_local",
            return_value=_fixed_now(2026, 7, 23),
        ):
            with pytest.raises(ValueError, match="Could not parse date"):
                _parse_date("sometime last week")


class TestSelectMatching:
    WALK = {"id": 1, "name": "Post-Run Walk", "type": "Walk", "sport_type": "Walk"}
    RUN = {"id": 2, "name": "Morning Run", "type": "Run", "sport_type": "Run"}

    def test_type_match_beats_name_substring(self):
        """'run' should pick the Run, not a Walk whose name mentions 'run'."""
        result = _select_matching([self.WALK, self.RUN], lambda a: a, "run")
        assert result == [self.RUN]

    def test_name_substring_used_when_no_type_match(self):
        afternoon = {**self.RUN, "id": 3, "name": "Afternoon Run"}
        result = _select_matching([self.RUN, afternoon], lambda a: a, "morning")
        assert result == [self.RUN]

    def test_exact_name_wins(self):
        result = _select_matching([self.WALK, self.RUN], lambda a: a, "morning run")
        assert result == [self.RUN]


class TestFormatWorkoutMarkdown:
    def test_run_basic_structure(self):
        """Test that run markdown has all expected sections."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "# Morning Run" in result
        assert "**Date:** 2026-03-19 (Thursday) 7:30 AM" in result
        assert "**Type:** Run" in result
        assert "**Sport Type:** Run" in result
        assert "**Workout Category:** Easy" in result
        assert "**Gear:** Altra Torin 7" in result
        assert "## Summary" in result
        assert "| Metric | Value |" in result
        assert "## Mile Splits" in result
        assert "## Subjective Notes" in result

    def test_run_summary_fields(self):
        """Test that run summary includes key metrics."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "6.20 mi" in result
        assert "52:14" in result
        assert "148 bpm" in result
        assert "165 bpm" in result
        assert "176 spm" in result  # 88 * 2
        assert "278 W" in result
        assert "650 kcal" in result
        assert "46°F" in result  # 8°C
        assert "COROS PACE 3" in result
        assert "Trainer | No" in result

    def test_run_training_metrics(self):
        """Test that subjective effort and achievement metrics are included."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "Perceived Exertion (RPE) | 6/10" in result
        assert "Relative Effort | 88" in result
        assert "PRs | 2" in result
        assert "Achievements | 5" in result

    def test_run_description(self):
        """Test that the Strava activity description is rendered."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "## Description" in result
        assert "> Felt strong on the back half." in result
        assert "> Legs a little heavy at the start." in result

    def test_no_description_omitted(self):
        """Test that the Description section is omitted when empty."""
        activity = {**SAMPLE_RUN_ACTIVITY, "description": ""}
        result = format_workout_markdown(activity)
        assert "## Description" not in result

    def test_run_mile_splits_columns(self):
        """Test that mile splits have all required columns."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "| Mile | Time | Pace | Avg HR | Elev Δ | GAP | Pace Zone |" in result
        # Verify fractional last split
        assert "| 0.20 |" in result  # 321.8m ~ 0.20 mi

    def test_run_best_efforts(self):
        """Test that best efforts section is included."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY)

        assert "## Best Efforts" in result
        assert "400m" in result
        assert "1 mile" in result

    def test_run_no_best_efforts(self):
        """Test that best efforts is omitted when not present."""
        activity = {**SAMPLE_RUN_ACTIVITY, "best_efforts": []}
        result = format_workout_markdown(activity)
        assert "## Best Efforts" not in result

    def test_run_with_zones(self):
        """Test that HR zones are included when provided."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY, zones=SAMPLE_ZONES)

        assert "## HR Zones" in result
        assert "| Zone | Name | Min HR | Max HR | Time | % of Total |" in result
        assert "Recovery" in result
        assert "Aerobic" in result

    def test_run_with_laps(self):
        """Test that laps section is included when >1 lap."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY, laps=SAMPLE_LAPS)

        assert "## Laps" in result
        assert "Warm Up" in result
        assert "Interval 1" in result
        assert "Cool Down" in result

    def test_run_single_lap_omitted(self):
        """Test that laps section is omitted with only 1 lap."""
        result = format_workout_markdown(SAMPLE_RUN_ACTIVITY, laps=[SAMPLE_LAPS[0]])
        assert "## Laps" not in result

    def test_ride_basic_structure(self):
        """Test that ride markdown uses ride template."""
        result = format_workout_markdown(SAMPLE_RIDE_ACTIVITY)

        assert "# Zwift Easy Spin" in result
        assert "**Type:** Ride" in result
        assert "**Sport Type:** VirtualRide" in result
        assert "## Summary" in result
        assert "## Mile Splits" not in result  # Rides don't have splits
        assert "## Best Efforts" not in result  # Rides don't have best efforts

    def test_ride_summary_fields(self):
        """Test that ride summary includes ride-specific metrics."""
        result = format_workout_markdown(SAMPLE_RIDE_ACTIVITY)

        assert "15.00 mi" in result
        assert "180 W" in result
        assert "320 W" in result
        assert "195 W" in result  # weighted NP
        assert "85 rpm" in result
        assert "486 kJ" in result
        assert "Trainer | Yes" in result
        assert "68°F" in result  # 20°C

    def test_strength_basic_structure(self):
        """Test that strength/other activity uses simple template."""
        result = format_workout_markdown(SAMPLE_STRENGTH_ACTIVITY)

        assert "# Gym Session" in result
        assert "**Type:** WeightTraining" in result
        assert "## Summary" in result
        assert "1:00:00" in result  # 3600s duration
        assert "120 bpm" in result
        assert "400 kcal" in result
        assert "## Mile Splits" not in result
        assert "## Best Efforts" not in result


class TestUpdateSection:
    def test_update_existing_section(self, test_config, tmp_path):
        """Test updating an existing section in a workout file."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19_morning-run.md"
        workout_file.write_text(
            "# Morning Run\n\n## Summary\n| Metric | Value |\n\n"
            "## Subjective Notes\n**Pre-run:**\n> \n"
        )

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section(
                "2026-03-19",
                "Subjective Notes",
                "**Pre-run:**\n> Slept well\n\n**During:**\n> Felt great",
            )

        assert "updated" in result
        content = workout_file.read_text()
        assert "Slept well" in content
        assert "Felt great" in content

    @pytest.mark.parametrize("bad_section", ["Summary", "Notes", "Mile Splits"])
    def test_update_section_rejects_unknown_section(
        self, test_config, tmp_path, bad_section
    ):
        """An unlisted section name is refused, leaving the file untouched.

        Regression: "Summary" matched the generated header and wiped the
        fetched Strava data, which _save_workout will not re-fetch over an
        existing file.
        """
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19_morning-run.md"
        original = (
            "# Morning Run\n\n## Summary\n| Metric | Value |\n"
            "| Distance | 6.20 mi |\n\n## Subjective Notes\n> \n"
        )
        workout_file.write_text(original)

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section("2026-03-19", bad_section, "felt easy")

        assert "Unknown section" in result
        assert workout_file.read_text() == original

    def test_add_new_section(self, test_config, tmp_path):
        """Test adding a new section that doesn't exist yet."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19_morning-run.md"
        workout_file.write_text("# Morning Run\n\n## Summary\n| Metric | Value |\n")

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section(
                "2026-03-19",
                "Context",
                "> Week 2 of training plan.",
            )

        assert "updated" in result
        content = workout_file.read_text()
        assert "## Context" in content
        assert "Week 2 of training plan" in content

    def test_add_fueling_section(self, test_config, tmp_path):
        """Test adding a fueling table."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        workout_file = workout_dir / "2026-03-19_morning-run.md"
        workout_file.write_text("# Morning Run\n\n## Summary\n| Metric | Value |\n")

        fueling_content = (
            "| Timing | Item | Carbs | Caffeine | Sodium | Water |\n"
            "|--------|------|-------|----------|--------|-------|\n"
            "| Pre | Oatmeal | 65g | — | — | 500mL |\n"
            "| During | Gel | 25g | 50mg | 200mg | — |"
        )

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section("2026-03-19", "Fueling", fueling_content)

        assert "updated" in result
        content = workout_file.read_text()
        assert "## Fueling" in content
        assert "Oatmeal" in content

    def test_update_no_file(self, test_config):
        """Test updating when no workout file exists."""
        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section("2026-03-19", "Context", "> test")

        assert "No workout file found" in result

    def test_update_ambiguous_multiple_files(self, test_config, tmp_path):
        """Two workouts on a date with no filter should refuse and list options."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        (workout_dir / "2026-03-19_afternoon-walk.md").write_text(
            "# Afternoon Walk\n**Type:** Walk\n**Sport Type:** Walk\n\n## Summary\n"
        )
        (workout_dir / "2026-03-19_morning-run.md").write_text(
            "# Morning Run\n**Type:** Run\n**Sport Type:** Run\n\n## Summary\n"
        )

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section("2026-03-19", "Context", "> test")

        assert "Multiple workout files" in result
        assert "Morning Run" in result
        assert "Afternoon Walk" in result

    def test_update_selects_by_type(self, test_config, tmp_path):
        """activity_type should target the right file among several on a date."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        walk = workout_dir / "2026-03-19_afternoon-walk.md"
        walk.write_text(
            "# Afternoon Walk\n**Type:** Walk\n**Sport Type:** Walk\n\n## Summary\n"
        )
        run = workout_dir / "2026-03-19_morning-run.md"
        run.write_text(
            "# Morning Run\n**Type:** Run\n**Sport Type:** Run\n\n## Summary\n"
        )

        with patch("app.agents.workout.workout_service.config", test_config):
            result = update_section(
                "2026-03-19", "Context", "> Felt good", activity_type="run"
            )

        assert "morning-run" in result
        assert "Felt good" in run.read_text()
        assert "Felt good" not in walk.read_text()


class TestGetWorkoutSummary:
    def test_get_summary(self, test_config, tmp_path):
        """Test reading a workout file."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        content = "# Morning Run\n\n## Summary\n"
        (workout_dir / "2026-03-19_morning-run.md").write_text(content)

        with patch("app.agents.workout.workout_service.config", test_config):
            result = get_workout_summary("2026-03-19")

        assert result == content

    def test_get_summary_not_found(self, test_config):
        """Test reading a non-existent workout file."""
        with patch("app.agents.workout.workout_service.config", test_config):
            result = get_workout_summary("2026-03-19")

        assert "No workout file found" in result

    def test_get_summary_selects_by_type(self, test_config, tmp_path):
        """activity_type should return the matching file among several on a date."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        (workout_dir / "2026-03-19_afternoon-walk.md").write_text(
            "# Afternoon Walk\n**Type:** Walk\n**Sport Type:** Walk\n\n## Summary\n"
        )
        run_content = (
            "# Morning Run\n**Type:** Run\n**Sport Type:** Run\n\n## Summary\n"
        )
        (workout_dir / "2026-03-19_morning-run.md").write_text(run_content)

        with patch("app.agents.workout.workout_service.config", test_config):
            result = get_workout_summary("2026-03-19", activity_type="run")

        assert result == run_content


class TestFetchLatestWorkout:
    @pytest.mark.asyncio
    async def test_fetch_latest_workout(self, test_config, tmp_path):
        """Test fetching and saving the latest workout."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.get_latest_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_RUN_ACTIVITY,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=SAMPLE_ZONES,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=SAMPLE_LAPS,
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_latest_workout()

        assert "Morning Run" in result
        assert "Saved" in result

        workout_dir = tmp_path / "workouts"
        files = list(workout_dir.glob("*.md"))
        assert len(files) == 1
        assert "2026-03-19" in files[0].name
        assert "morning-run" in files[0].name

    @pytest.mark.asyncio
    async def test_fetch_latest_workout_by_type(self, test_config, tmp_path):
        """activity_type should grab the most recent activity of that kind."""
        walk = {
            **SAMPLE_RUN_ACTIVITY,
            "id": 999,
            "name": "Evening Walk",
            "type": "Walk",
            "sport_type": "Walk",
        }
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_recent_activities",
                new_callable=AsyncMock,
                return_value=[walk, SAMPLE_RUN_ACTIVITY],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_RUN_ACTIVITY,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_latest_workout(activity_type="run")

        assert "Saved" in result
        assert "Morning Run" in result

    @pytest.mark.asyncio
    async def test_fetch_latest_workout_by_type_skips_name_substring_match(
        self, test_config, tmp_path
    ):
        """A newer Walk named 'Post-Run Walk' must not shadow the actual run."""
        walk = {
            **SAMPLE_RUN_ACTIVITY,
            "id": 999,
            "name": "Post-Run Walk",
            "type": "Walk",
            "sport_type": "Walk",
        }
        get_activity = AsyncMock(return_value=SAMPLE_RUN_ACTIVITY)
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_recent_activities",
                new_callable=AsyncMock,
                return_value=[walk, SAMPLE_RUN_ACTIVITY],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new=get_activity,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_latest_workout(activity_type="run")

        assert "Morning Run" in result
        get_activity.assert_awaited_once_with(SAMPLE_RUN_ACTIVITY["id"])

    @pytest.mark.asyncio
    async def test_fetch_latest_workout_by_type_no_match(self, test_config):
        """activity_type with no recent match should report none found."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_recent_activities",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_latest_workout(activity_type="ride")

        assert "No recent 'ride' activity found" in result


class TestFetchWorkoutByDate:
    @pytest.mark.asyncio
    async def test_fetch_workout_by_date(self, test_config, tmp_path):
        """Test fetching a workout by date when there is a single activity."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_RUN_ACTIVITY,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19")

        assert "Saved" in result

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_not_found(self, test_config):
        """Test fetching a workout when none exists for the date."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19")

        assert "No activity found" in result

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_multiple_ambiguous(self, test_config):
        """Multiple activities with no filter should list the options, not save."""
        get_activity = AsyncMock()
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY, SAMPLE_STRENGTH_ACTIVITY],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new=get_activity,
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19")

        assert "Multiple activities" in result
        assert "Morning Run" in result
        assert "Gym Session" in result
        get_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_type_filter_selects(
        self, test_config, tmp_path
    ):
        """An activity_type filter should pick the matching activity among several."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY, SAMPLE_STRENGTH_ACTIVITY],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_RUN_ACTIVITY,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19", activity_type="run")

        assert "Saved" in result
        assert "Morning Run" in result

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_type_filter_no_match(self, test_config):
        """A filter that matches nothing should report what is available."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await fetch_workout_by_date("2026-03-19", activity_type="ride")

        assert "No 'ride' activity found" in result
        assert "Morning Run" in result

    @pytest.mark.asyncio
    async def test_fetch_workout_by_date_two_runs_disambiguated_by_name(
        self, test_config, tmp_path
    ):
        """Two same-type activities should be selectable by name (e.g. 'morning run')."""
        afternoon_run = {
            **SAMPLE_RUN_ACTIVITY,
            "id": 222,
            "name": "Afternoon Run",
            "start_date": "2026-03-19T21:00:00Z",
            "start_date_local": "2026-03-19T14:00:00",
        }
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY, afternoon_run],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity",
                new_callable=AsyncMock,
                return_value=SAMPLE_RUN_ACTIVITY,
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_zones",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.agents.workout.workout_service.strava_client.get_activity_laps",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            # 'run' alone is ambiguous between the two runs
            ambiguous = await fetch_workout_by_date("2026-03-19", activity_type="run")
            # 'morning run' (the activity name) resolves it
            resolved = await fetch_workout_by_date(
                "2026-03-19", activity_type="morning run"
            )

        assert "Multiple activities" in ambiguous
        assert "Saved" in resolved
        assert "Morning Run" in resolved


class TestSaveWorkout:
    def test_same_day_same_name_different_activity_gets_suffix(self, test_config):
        """Two same-day activities sharing a name must both be persisted."""
        first = SAMPLE_RUN_ACTIVITY
        second = {
            **SAMPLE_RUN_ACTIVITY,
            "id": 22222,
            "start_date_local": "2026-03-19T18:00:00",
        }
        with patch("app.agents.workout.workout_service.config", test_config):
            path1, saved1 = _save_workout(first, format_workout_markdown(first))
            path2, saved2 = _save_workout(second, format_workout_markdown(second))
            # Re-saving either activity keeps its own existing file
            repath1, resaved1 = _save_workout(first, format_workout_markdown(first))
            repath2, resaved2 = _save_workout(second, format_workout_markdown(second))

        assert saved1 is True and saved2 is True
        assert path1.name == "2026-03-19_morning-run.md"
        assert path2.name == "2026-03-19_morning-run-2.md"
        assert (repath1, resaved1) == (path1, False)
        assert (repath2, resaved2) == (path2, False)

    def test_legacy_file_without_id_is_kept(self, test_config, tmp_path):
        """An existing file with no recorded id is treated as the same activity."""
        workout_dir = tmp_path / "workouts"
        workout_dir.mkdir()
        legacy = workout_dir / "2026-03-19_morning-run.md"
        legacy.write_text("# Morning Run\n**Type:** Run\n\n## Summary\n")

        with patch("app.agents.workout.workout_service.config", test_config):
            path, saved = _save_workout(
                SAMPLE_RUN_ACTIVITY, format_workout_markdown(SAMPLE_RUN_ACTIVITY)
            )

        assert path == legacy
        assert saved is False
        assert "## Summary" in legacy.read_text()


class TestListWorkoutsOnDate:
    @pytest.mark.asyncio
    async def test_list_workouts_on_date(self, test_config):
        """Listing should enumerate every activity on the date."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[SAMPLE_RUN_ACTIVITY, SAMPLE_STRENGTH_ACTIVITY],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await list_workouts_on_date("2026-03-19")

        assert "Found 2 activities" in result
        assert "1. Morning Run" in result
        assert "2. Gym Session" in result

    @pytest.mark.asyncio
    async def test_list_workouts_on_date_none(self, test_config):
        """Listing with no activities should report none found."""
        with (
            patch(
                "app.agents.workout.workout_service.strava_client.list_activities_on_date",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.agents.workout.workout_service.config", test_config),
        ):
            result = await list_workouts_on_date("2026-03-19")

        assert "No activity found" in result
