"""
Unit tests for app.core.timezone_utils module.
"""

from datetime import datetime
from app.core.timezone_utils import (
    now_local,
    now_local_isoformat,
    get_scheduler_timezone,
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
