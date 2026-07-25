"""
Unit tests for app.core.timezone_utils module.
"""

from datetime import datetime, timedelta
from app.core.timezone_utils import (
    ensure_timezone,
    get_scheduler_timezone,
    now_local,
    now_local_isoformat,
    parse_datetime_in_app_tz,
)


class TestTimezoneUtils:
    """Test timezone utility functions."""

    def test_now_local_returns_timezone_aware_datetime(self):
        """Test that now_local() returns a timezone-aware datetime in local timezone."""
        dt = now_local()

        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert str(dt.tzinfo) == "America/Los_Angeles"

    def test_now_local_isoformat_returns_string(self):
        """Test that now_local_isoformat() returns an ISO format string."""
        iso_str = now_local_isoformat()

        assert isinstance(iso_str, str)
        # Should contain timezone offset for local timezone
        assert "T" in iso_str  # ISO format separator
        assert "-" in iso_str or "+" in iso_str  # Should have timezone info

    def test_get_scheduler_timezone(self):
        """Test getting scheduler timezone from config."""
        timezone = get_scheduler_timezone()

        assert hasattr(timezone, "zone")  # Check it's a pytz timezone
        # Should return the configured timezone (America/Los_Angeles by default)
        assert str(timezone) == "America/Los_Angeles"


class TestDstTransitions:
    """DST-transition handling for naive datetimes (America/Los_Angeles)."""

    def test_nonexistent_spring_forward_time_shifts_forward(self):
        # 2025-03-09 02:30 does not exist (clocks jump 02:00 -> 03:00)
        dt = ensure_timezone(datetime(2025, 3, 9, 2, 30))
        assert (dt.hour, dt.minute) == (3, 30)
        assert dt.utcoffset() == timedelta(hours=-7)  # PDT

    def test_ambiguous_fall_back_time_resolves_to_dst(self):
        # 2025-11-02 01:30 occurs twice; the first (DST) occurrence wins
        dt = ensure_timezone(datetime(2025, 11, 2, 1, 30))
        assert dt.utcoffset() == timedelta(hours=-7)  # PDT

    def test_parse_datetime_in_app_tz_handles_nonexistent_time(self):
        dt = parse_datetime_in_app_tz("2025-03-09T02:30:00")
        assert (dt.hour, dt.minute) == (3, 30)
        assert dt.utcoffset() == timedelta(hours=-7)

    def test_normal_time_unaffected(self):
        dt = ensure_timezone(datetime(2025, 7, 1, 12, 0))
        assert (dt.hour, dt.minute) == (12, 0)
        assert dt.utcoffset() == timedelta(hours=-7)
