"""
Home Assistant location service for fetching phone GPS coordinates.
"""

import httpx
from loguru import logger

from app.core.settings import config


async def get_phone_location() -> tuple[float | None, float | None]:
    """
    Get phone location from Home Assistant device tracker.

    Returns:
        Tuple of (latitude, longitude), or (None, None) if unavailable.
    """
    if not config.home_assistant_url or not config.home_assistant_token:
        logger.warning("Home Assistant URL or token not configured")
        return None, None

    entity_id = config.home_assistant_phone_entity_id
    if not entity_id:
        logger.warning("Home Assistant phone entity ID not configured")
        return None, None

    url = f"{config.home_assistant_url}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {config.home_assistant_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

        data = response.json()
        attributes = data.get("attributes", {})
        latitude = attributes.get("latitude")
        longitude = attributes.get("longitude")

        if latitude is None or longitude is None:
            logger.warning(f"Location attributes missing from HA entity '{entity_id}'")
            return None, None

        return float(latitude), float(longitude)

    except Exception as e:
        logger.warning(f"Failed to get phone location from Home Assistant: {e}")
        return None, None
