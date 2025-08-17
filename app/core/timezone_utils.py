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
