"""Tests for the Strava API client."""

import time

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.workout import strava_client


@pytest.fixture(autouse=True)
def reset_token_cache():
    """Reset module-level token cache between tests."""
    strava_client._access_token = None
    strava_client._token_expires_at = 0
    yield
    strava_client._access_token = None
    strava_client._token_expires_at = 0


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_get_access_token_refreshes(self):
        """Test that get_access_token calls Strava OAuth endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_token_123",
            "expires_at": time.time() + 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.agents.workout.strava_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            token = await strava_client.get_access_token()

        assert token == "new_token_123"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_access_token_uses_cache(self):
        """Test that cached token is returned if not expired."""
        strava_client._access_token = "cached_token"
        strava_client._token_expires_at = time.time() + 3600

        token = await strava_client.get_access_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_access_token_refreshes_within_expiry_margin(self):
        """A token expiring within the safety margin should be refreshed early."""
        strava_client._access_token = "stale_token"
        strava_client._token_expires_at = time.time() + 30  # inside 60s margin

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_token_456",
            "expires_at": time.time() + 3600,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.agents.workout.strava_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            token = await strava_client.get_access_token()

        assert token == "new_token_456"
        mock_client.post.assert_called_once()


class TestGetLatestActivity:
    @pytest.mark.asyncio
    async def test_get_latest_activity(self):
        """Test fetching the latest activity."""
        activities_response = MagicMock()
        activities_response.json.return_value = [{"id": 12345}]
        activities_response.raise_for_status = MagicMock()

        detail_response = MagicMock()
        detail_response.json.return_value = {
            "id": 12345,
            "distance": 10000,
            "moving_time": 3000,
            "type": "Run",
        }
        detail_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [activities_response, detail_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.get_latest_activity()

        assert result["id"] == 12345

    @pytest.mark.asyncio
    async def test_get_latest_activity_no_activities(self):
        """Test that ValueError is raised when no activities exist."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            with pytest.raises(ValueError, match="No activities found"):
                await strava_client.get_latest_activity()


class TestListRecentActivities:
    @pytest.mark.asyncio
    async def test_list_recent_activities_sorted_recent_first(self):
        """Recent activities should be returned most-recent-first, no detail fetch."""
        activities_response = MagicMock()
        activities_response.json.return_value = [
            {"id": 111, "type": "Run", "start_date": "2026-03-18T14:00:00Z"},
            {"id": 222, "type": "Walk", "start_date": "2026-03-19T22:00:00Z"},
        ]
        activities_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = activities_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.list_recent_activities()

        assert [a["id"] for a in result] == [222, 111]


class TestListActivitiesOnDate:
    @pytest.mark.asyncio
    async def test_list_activities_on_date_found(self):
        """Test listing all activity summaries for a date, sorted earliest-first."""
        from datetime import datetime

        activities_response = MagicMock()
        activities_response.json.return_value = [
            {"id": 222, "type": "Walk", "start_date": "2026-03-19T22:00:00Z"},
            {"id": 111, "type": "Run", "start_date": "2026-03-19T14:00:00Z"},
        ]
        activities_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = activities_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.list_activities_on_date(
                datetime(2026, 3, 19, tzinfo=None)
            )

        # Returns the full list, no detail fetch, sorted earliest-first
        assert [a["id"] for a in result] == [111, 222]

    @pytest.mark.asyncio
    async def test_list_activities_on_date_empty(self):
        """Test that an empty list is returned when no activities found on date."""
        from datetime import datetime

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.list_activities_on_date(
                datetime(2026, 3, 19, tzinfo=None)
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_list_activities_on_date_dst_fall_back_covers_full_day(self):
        """On a DST fall-back day the query window must span the full 25 hours."""
        import pytz
        from datetime import datetime

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
            patch(
                "app.agents.workout.strava_client.get_local_timezone",
                return_value=pytz.timezone("America/Los_Angeles"),
            ),
        ):
            # 2025-11-02: US DST fall-back — the day is 25 hours long
            await strava_client.list_activities_on_date(datetime(2025, 11, 2))

        params = mock_client.get.call_args.kwargs["params"]
        assert params["before"] - params["after"] == 25 * 3600 - 1


class TestGetActivityZones:
    @pytest.mark.asyncio
    async def test_get_activity_zones(self):
        """Test fetching activity zones."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"type": "heartrate", "distribution_buckets": []}
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.get_activity_zones(12345)

        assert len(result) == 1
        assert result[0]["type"] == "heartrate"


class TestGetActivityLaps:
    @pytest.mark.asyncio
    async def test_get_activity_laps(self):
        """Test fetching activity laps."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "Lap 1", "distance": 1609.34, "moving_time": 500}
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.agents.workout.strava_client.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "app.agents.workout.strava_client.get_access_token",
                return_value="token",
            ),
        ):
            result = await strava_client.get_activity_laps(12345)

        assert len(result) == 1
        assert result[0]["name"] == "Lap 1"
