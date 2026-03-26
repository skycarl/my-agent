"""
Tests for the Home Assistant location service.
"""

from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from app.agents.logger.location_service import get_phone_location


@pytest.fixture
def ha_config():
    """Patch config with Home Assistant settings."""
    with patch("app.agents.logger.location_service.config") as mock_config:
        mock_config.home_assistant_url = "http://homeassistant.local:8123"
        mock_config.home_assistant_token = "test-token"
        mock_config.home_assistant_phone_entity_id = "device_tracker.pixel_7"
        yield mock_config


class TestGetPhoneLocation:
    @pytest.mark.asyncio
    async def test_success(self, ha_config):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "entity_id": "device_tracker.pixel_7",
            "state": "home",
            "attributes": {
                "latitude": 47.6062,
                "longitude": -122.3321,
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "app.agents.logger.location_service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            lat, lon = await get_phone_location()

        assert lat == 47.6062
        assert lon == -122.3321

    @pytest.mark.asyncio
    async def test_unreachable(self, ha_config):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch(
            "app.agents.logger.location_service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            lat, lon = await get_phone_location()

        assert lat is None
        assert lon is None

    @pytest.mark.asyncio
    async def test_missing_attributes(self, ha_config):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "entity_id": "device_tracker.pixel_7",
            "state": "unknown",
            "attributes": {},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "app.agents.logger.location_service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            lat, lon = await get_phone_location()

        assert lat is None
        assert lon is None

    @pytest.mark.asyncio
    async def test_no_url_configured(self):
        with patch("app.agents.logger.location_service.config") as mock_config:
            mock_config.home_assistant_url = ""
            mock_config.home_assistant_token = "test-token"

            lat, lon = await get_phone_location()

        assert lat is None
        assert lon is None

    @pytest.mark.asyncio
    async def test_no_token_configured(self):
        with patch("app.agents.logger.location_service.config") as mock_config:
            mock_config.home_assistant_url = "http://ha.local:8123"
            mock_config.home_assistant_token = ""

            lat, lon = await get_phone_location()

        assert lat is None
        assert lon is None
