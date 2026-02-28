"""
Tests for app.core.task_manager — TaskManager._execute_api_call and execute_task.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.settings import Config
from app.models.tasks import APICallConfig, TaskConfig, TaskSchedule

pytestmark = [pytest.mark.unit, pytest.mark.app]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config(tmp_path, monkeypatch):
    """Isolated Config pointing at a temp storage directory."""
    cfg = Config.create_test_config(
        storage_path=str(tmp_path),
        app_url="http://test-host:8000",
        x_token="test-token-abc",
        authorized_user_id=12345,
    )
    monkeypatch.setattr("app.core.task_manager.config", cfg)
    return cfg


@pytest.fixture()
def task_manager_instance(test_config):
    """Create a fresh TaskManager without loading results from disk."""
    from app.core.task_manager import TaskManager

    return TaskManager()


def _make_api_task(
    endpoint="/agent_response",
    method="POST",
    payload=None,
    headers=None,
    timeout=120,
    max_retries=0,
    retry_delay=0,
    enabled=True,
) -> TaskConfig:
    """Build a minimal TaskConfig for testing."""
    return TaskConfig(
        id="task-1",
        name="Test Task",
        type="api_call",
        enabled=enabled,
        schedule=TaskSchedule(type="cron", expression="0 7 * * *"),
        api_call=APICallConfig(
            endpoint=endpoint,
            method=method,
            payload=payload or {"input": "hi"},
            headers=headers,
            timeout=timeout,
        ),
        max_retries=max_retries,
        retry_delay=retry_delay,
    )


# ===========================================================================
# _execute_api_call tests
# ===========================================================================


class TestExecuteApiCall:
    @pytest.mark.asyncio
    async def test_successful_post(self, task_manager_instance):
        """A 200 POST response returns (True, {status_code, response})."""
        task = _make_api_task()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, data = await task_manager_instance._execute_api_call(task)

        assert success is True
        assert data["status_code"] == 200
        assert data["response"] == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_non_2xx_returns_failure(self, task_manager_instance):
        """A 500 response returns (False, {status_code, response, error})."""
        task = _make_api_task()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "server error"}

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, data = await task_manager_instance._execute_api_call(task)

        assert success is False
        assert data["status_code"] == 500
        assert "error" in data

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self, task_manager_instance):
        """An httpx.TimeoutException returns (False, {error})."""
        task = _make_api_task()

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, data = await task_manager_instance._execute_api_call(task)

        assert success is False
        assert "error" in data
        assert "timed out" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_disallowed_endpoint_rejected(self, task_manager_instance):
        """Endpoints not in ALLOWED_TASK_ENDPOINTS are rejected."""
        task = _make_api_task(endpoint="/admin/delete")

        success, data = await task_manager_instance._execute_api_call(task)

        assert success is False
        assert "not allowed" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_custom_headers_cannot_override_x_token(self, task_manager_instance):
        """Custom headers in the task cannot override the X-Token header."""
        task = _make_api_task(headers={"X-Token": "evil-override"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, _ = await task_manager_instance._execute_api_call(task)

        # Grab the actual headers passed to post()
        call_kwargs = client_instance.post.call_args
        sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get(
            "headers"
        )
        assert sent_headers["X-Token"] == "test-token-abc"

    @pytest.mark.asyncio
    async def test_no_api_call_config(self, task_manager_instance):
        """If api_call is None, returns (False, {error})."""
        task = _make_api_task()
        task.api_call = None

        success, data = await task_manager_instance._execute_api_call(task)

        assert success is False
        assert "no api call" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_get_method(self, task_manager_instance):
        """GET requests go through the client.get path."""
        task = _make_api_task(method="GET")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, data = await task_manager_instance._execute_api_call(task)

        assert success is True
        client_instance.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_method(self, task_manager_instance):
        """Unsupported HTTP methods return (False, {error})."""
        task = _make_api_task(method="DELETE")

        with patch("app.core.task_manager.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            success, data = await task_manager_instance._execute_api_call(task)

        assert success is False
        assert "unsupported" in data["error"].lower()


# ===========================================================================
# execute_task tests
# ===========================================================================


class TestExecuteTask:
    @pytest.mark.asyncio
    async def test_retry_logic_fail_then_succeed(self, task_manager_instance):
        """execute_task retries until _execute_api_call succeeds."""
        task = _make_api_task(max_retries=2, retry_delay=0)

        call_count = 0

        async def mock_api_call(t):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return False, {"error": "transient error"}
            return True, {"status_code": 200, "response": {"ok": True}}

        with patch.object(
            task_manager_instance,
            "_execute_api_call",
            side_effect=mock_api_call,
        ):
            result = await task_manager_instance.execute_task(task)

        assert result.success is True
        assert result.retry_count == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_exhausted(self, task_manager_instance):
        """When all retries fail, result.success is False."""
        task = _make_api_task(max_retries=1, retry_delay=0)

        with patch.object(
            task_manager_instance,
            "_execute_api_call",
            new_callable=AsyncMock,
            return_value=(False, {"error": "persistent failure"}),
        ):
            with patch.object(
                task_manager_instance,
                "_notify_error_via_endpoint",
                new_callable=AsyncMock,
            ):
                result = await task_manager_instance.execute_task(task)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_error_notification_sent_on_failure(self, task_manager_instance):
        """On failure the manager calls _notify_error_via_endpoint."""
        task = _make_api_task(max_retries=0, retry_delay=0)

        mock_notify = AsyncMock()
        with patch.object(
            task_manager_instance,
            "_execute_api_call",
            new_callable=AsyncMock,
            return_value=(False, {"error": "boom"}),
        ):
            with patch.object(
                task_manager_instance,
                "_notify_error_via_endpoint",
                mock_notify,
            ):
                await task_manager_instance.execute_task(task)

        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_primary_action(self, task_manager_instance):
        """An exception during execution is caught and stored."""
        task = _make_api_task(max_retries=0)

        with patch.object(
            task_manager_instance,
            "_execute_api_call",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            with patch.object(
                task_manager_instance,
                "_notify_error_via_endpoint",
                new_callable=AsyncMock,
            ):
                result = await task_manager_instance.execute_task(task)

        assert result.success is False
        assert result.error_message == "unexpected"

    @pytest.mark.asyncio
    async def test_result_stored_after_execution(self, task_manager_instance):
        """After execution, the result is persisted in results_storage."""
        task = _make_api_task(max_retries=0)

        with patch.object(
            task_manager_instance,
            "_execute_api_call",
            new_callable=AsyncMock,
            return_value=(True, {"status_code": 200, "response": {}}),
        ):
            await task_manager_instance.execute_task(task)

        assert len(task_manager_instance.results_storage.results) == 1
        assert task_manager_instance.results_storage.results[0].task_id == "task-1"
