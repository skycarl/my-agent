"""
Strava API client with OAuth2 token refresh.

Handles authentication and activity fetching from the Strava API.
"""

import time
from datetime import datetime

import httpx
from loguru import logger

from app.core.settings import config

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Module-level token cache
_access_token: str | None = None
_token_expires_at: float = 0


async def get_access_token() -> str:
    """Get a valid access token, refreshing if expired."""
    global _access_token, _token_expires_at

    if _access_token and time.time() < _token_expires_at:
        return _access_token

    async with httpx.AsyncClient() as client:
        response = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": config.strava_client_id,
                "client_secret": config.strava_client_secret,
                "refresh_token": config.strava_refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()

    _access_token = data["access_token"]
    _token_expires_at = data["expires_at"]
    logger.debug("Strava access token refreshed")
    return _access_token


async def _get_headers() -> dict[str, str]:
    token = await get_access_token()
    return {"Authorization": f"Bearer {token}"}


async def get_activity(activity_id: int) -> dict:
    """Fetch full activity detail by ID."""
    headers = await _get_headers()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/activities/{activity_id}",
            headers=headers,
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()


async def get_latest_activity() -> dict:
    """Fetch the most recent activity with full detail."""
    headers = await _get_headers()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers=headers,
            params={"per_page": 1},
            timeout=15.0,
        )
        response.raise_for_status()
        activities = response.json()

    if not activities:
        raise ValueError("No activities found on Strava")

    return await get_activity(activities[0]["id"])


async def get_activities_on_date(target_date: datetime) -> dict | None:
    """Fetch the first Run activity on a given date, or None if not found."""
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=0)

    headers = await _get_headers()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers=headers,
            params={
                "after": int(start_of_day.timestamp()),
                "before": int(end_of_day.timestamp()),
                "per_page": 30,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        activities = response.json()

    # Filter to runs
    runs = [a for a in activities if a.get("type") == "Run"]
    if not runs:
        return None

    return await get_activity(runs[0]["id"])
