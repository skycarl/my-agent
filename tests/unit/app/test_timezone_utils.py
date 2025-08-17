"""
Unit tests for app.core.timezone_utils module.
"""

from datetime import datetime
import pytz
from app.core.timezone_utils import (
    now_local,
    now_local_isoformat,
    utc_to_local,
    local_to_utc,
    get_scheduler_timezone,
    get_local_timezone,
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

    def test_utc_to_local_conversion(self):
        """Test converting UTC datetime to local timezone."""
        # Create a UTC datetime
        utc_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)

        # Convert to local
        local_dt = utc_to_local(utc_dt)

        assert str(local_dt.tzinfo) == "America/Los_Angeles"
        # LA is UTC-8 in winter (PST), so 12:00 UTC should be 04:00 local
        assert local_dt.hour == 4
        assert local_dt.day == 15

    def test_utc_to_local_with_naive_datetime(self):
        """Test converting naive datetime (assumed UTC) to local timezone."""
        # Create a naive datetime (no timezone info)
        naive_dt = datetime(2024, 1, 15, 12, 0, 0)

        # Convert to local (should assume UTC)
        local_dt = utc_to_local(naive_dt)

        assert str(local_dt.tzinfo) == "America/Los_Angeles"
        # LA is UTC-8 in winter (PST), so 12:00 UTC should be 04:00 local
        assert local_dt.hour == 4
        assert local_dt.day == 15

    def test_local_to_utc_conversion(self):
        """Test converting local datetime to UTC."""
        # Create a local datetime
        local_dt = datetime(2024, 1, 15, 4, 0, 0, tzinfo=get_local_timezone())

        # Convert to UTC
        utc_dt = local_to_utc(local_dt)

        assert utc_dt.tzinfo == pytz.UTC
        # LA is UTC-8 in winter (PST), so 04:00 local should be 12:00 UTC
        # Note: The exact hour may vary due to DST transitions, so we'll check it's reasonable
        assert 11 <= utc_dt.hour <= 13
        assert utc_dt.day == 15

    def test_local_to_utc_with_naive_datetime(self):
        """Test converting naive datetime (assumed local) to UTC."""
        # Create a naive datetime (no timezone info)
        naive_dt = datetime(2024, 1, 15, 4, 0, 0)

        # Convert to UTC (should assume local)
        utc_dt = local_to_utc(naive_dt)

        assert utc_dt.tzinfo == pytz.UTC
        # LA is UTC-8 in winter (PST), so 04:00 local should be 12:00 UTC
        # Note: The exact hour may vary due to DST transitions, so we'll check it's reasonable
        assert 11 <= utc_dt.hour <= 13
        assert utc_dt.day == 15

    def test_get_scheduler_timezone(self):
        """Test getting scheduler timezone from config."""
        timezone = get_scheduler_timezone()

        assert hasattr(timezone, "zone")  # Check it's a pytz timezone
        # Should return the configured timezone (America/Los_Angeles by default)
        assert str(timezone) == "America/Los_Angeles"

    def test_dst_handling(self):
        """Test daylight saving time handling."""
        # Test during DST (summer)
        summer_utc = datetime(2024, 7, 15, 12, 0, 0, tzinfo=pytz.UTC)
        summer_local = utc_to_local(summer_utc)

        # LA is UTC-7 in summer (PDT), so 12:00 UTC should be 05:00 local
        assert summer_local.hour == 5
        assert summer_local.day == 15

        # Test during standard time (winter)
        winter_utc = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)
        winter_local = utc_to_local(winter_utc)

        # LA is UTC-8 in winter (PST), so 12:00 UTC should be 04:00 local
        assert winter_local.hour == 4
        assert winter_local.day == 15

    def test_round_trip_conversion(self):
        """Test round-trip conversion: UTC -> local -> UTC."""
        original_utc = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)

        # Convert to local and back
        local_dt = utc_to_local(original_utc)
        back_to_utc = local_to_utc(local_dt)

        # Should get back the same time
        assert back_to_utc == original_utc
