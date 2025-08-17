"""
Centralized timezone utilities for the application.

This module provides timezone-aware datetime functions to ensure consistent
timezone handling across the entire application.
"""

from datetime import datetime
import pytz
from app.core.settings import config


def get_local_timezone():
    """
    Get the configured local timezone from settings.

    Returns:
        pytz timezone object for the configured local timezone
    """
    return pytz.timezone(config.timezone)


def now_local() -> datetime:
    """
    Get current datetime in the configured local timezone.

    Returns:
        Current datetime in the configured local timezone
    """
    return datetime.now(get_local_timezone())


def now_local_isoformat() -> str:
    """
    Get current datetime in the configured local timezone as ISO format string.

    Returns:
        Current datetime in the configured local timezone as ISO format string
    """
    return now_local().isoformat()


def utc_to_local(utc_datetime: datetime) -> datetime:
    """
    Convert UTC datetime to the configured local timezone.

    Args:
        utc_datetime: UTC datetime object

    Returns:
        Datetime in the configured local timezone
    """
    if utc_datetime.tzinfo is None:
        # Assume UTC if no timezone info
        utc_datetime = pytz.UTC.localize(utc_datetime)
    return utc_datetime.astimezone(get_local_timezone())


def local_to_utc(local_datetime: datetime) -> datetime:
    """
    Convert local datetime to UTC.

    Args:
        local_datetime: Local datetime object

    Returns:
        Datetime in UTC
    """
    if local_datetime.tzinfo is None:
        # Assume local timezone if no timezone info
        local_datetime = get_local_timezone().localize(local_datetime)
    return local_datetime.astimezone(pytz.UTC)


def get_scheduler_timezone():
    """
    Get the configured scheduler timezone from settings.

    Returns:
        pytz timezone object for the configured scheduler timezone
    """
    return pytz.timezone(config.scheduler_timezone)


def parse_datetime_in_app_tz(dt_str_or_obj) -> datetime:
    """
    Parse a datetime input (string or datetime) and return a timezone-aware datetime
    in the application's default timezone (config.timezone) if naive.

    - If input is a string, attempt to parse ISO-8601 first via datetime.fromisoformat.
      If parsing fails, raise a helpful ValueError.
    - If the parsed/received datetime is naive, assume app timezone (config.timezone).
    - If it has a timezone, return as-is.
    """
    try:
        if isinstance(dt_str_or_obj, datetime):
            candidate = dt_str_or_obj
        else:
            # Attempt ISO-8601 parse (supports YYYY-MM-DDTHH:MM:SS[.ffffff][+/-HH:MM])
            candidate = datetime.fromisoformat(str(dt_str_or_obj))
    except Exception as e:
        raise ValueError(
            f"Failed to parse datetime input '{dt_str_or_obj}'. Provide ISO-8601 like '2025-09-01T09:00:00-07:00' or '2025-09-01T09:00:00'. Error: {e}"
        )

    if candidate.tzinfo is None:
        # Localize to app timezone
        return get_local_timezone().localize(candidate)
    return candidate


def parse_datetime_in_scheduler_tz(dt_str_or_obj) -> datetime:
    """
    Parse a datetime input (string or datetime) and return a timezone-aware datetime
    in the scheduler's timezone if naive.

    This is used for scheduling one-time (date) tasks where the scheduler timezone
    determines the interpretation of naive times.
    """
    dt = parse_datetime_in_app_tz(dt_str_or_obj)
    # Convert to scheduler timezone if needed
    return dt.astimezone(get_scheduler_timezone())


def ensure_timezone(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in the app's timezone if naive."""
    if dt.tzinfo is None:
        return get_local_timezone().localize(dt)
    return dt
