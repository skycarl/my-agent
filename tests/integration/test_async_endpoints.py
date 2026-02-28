"""
Integration tests for the async architecture endpoints.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app


class TestAsyncEndpoints:
    """Test the async architecture endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers with authentication token."""
        return {"X-Token": "12345678910"}

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        with patch("app.core.main_router.config") as mock_config:
            with patch("app.core.auth.config") as auth_config:
                mock_config.openai_api_key = "test-key"
                mock_config.valid_openai_models = ["gpt-5-mini", "gpt-5"]
                mock_config.default_model = "gpt-5-mini"
                mock_config.openai_timeout = 30
                mock_config.openai_max_retries = 3
                mock_config.authorized_user_id = 12345
                mock_config.max_conversation_history = 10
                mock_config.x_token = "12345678910"

                # Also mock the auth config
                auth_config.x_token = "12345678910"
                auth_config.authorized_user_id = 12345

                yield mock_config

    @pytest.fixture
    def mock_session(self):
        """Mock SDK session."""
        with patch("app.core.main_router.get_session") as mock_get_session:
            mock_sess = MagicMock()
            mock_sess.clear_session = AsyncMock()
            mock_get_session.return_value = mock_sess
            yield mock_sess

    @pytest.fixture
    def mock_agent_runner(self):
        """Mock the agents Runner."""
        with patch("app.core.main_router.Runner") as mock_runner:
            mock_result = MagicMock()
            mock_result.final_output = "Test agent response"
            mock_runner.run = AsyncMock(return_value=mock_result)
            yield mock_runner

    @pytest.fixture
    def mock_telegram_client(self):
        """Mock Telegram client."""
        with patch("app.core.telegram_client.telegram_client") as mock_client:
            mock_client.send_message = AsyncMock(return_value=(True, "msg_123"))
            yield mock_client

    def test_agent_response_endpoint_success(
        self,
        client,
        auth_headers,
        mock_config,
        mock_session,
        mock_agent_runner,
        mock_telegram_client,
    ):
        """Test successful agent response processing."""
        with patch(
            "app.core.main_router.create_orchestrator_agent"
        ) as mock_create_agent:
            with patch(
                "app.core.agent_response_handler.AgentResponseHandler"
            ) as mock_handler:
                mock_agent = MagicMock()
                mock_create_agent.return_value = mock_agent
                mock_handler.process_user_query_response = AsyncMock(
                    return_value=(True, "Response message")
                )

                response = client.post(
                    "/agent_response",
                    json={"input": "Hello, how are you?"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["response_sent"] is True

                # Verify agent was run with session
                mock_agent_runner.run.assert_called_once()
                call_kwargs = mock_agent_runner.run.call_args
                assert call_kwargs.kwargs.get("session") is mock_session

                # Verify Telegram message was sent
                mock_telegram_client.send_message.assert_called_once()

    def test_agent_response_endpoint_no_response_needed(
        self,
        client,
        auth_headers,
        mock_config,
        mock_session,
        mock_agent_runner,
    ):
        """Test when agent determines no response is needed."""
        with patch("app.core.main_router.create_orchestrator_agent"):
            with patch(
                "app.core.agent_response_handler.AgentResponseHandler"
            ) as mock_handler:
                mock_handler.process_user_query_response = AsyncMock(
                    return_value=(False, "")
                )

                response = client.post(
                    "/agent_response",
                    json={"input": "Test input"},
                    headers=auth_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["response_sent"] is False

    def test_agent_response_endpoint_with_messages(
        self,
        client,
        auth_headers,
        mock_config,
        mock_session,
        mock_agent_runner,
        mock_telegram_client,
    ):
        """Test agent response with conversation messages."""
        with patch("app.core.main_router.create_orchestrator_agent"):
            with patch(
                "app.core.agent_response_handler.AgentResponseHandler"
            ) as mock_handler:
                mock_handler.process_user_query_response = AsyncMock(
                    return_value=(True, "Response message")
                )

                messages = [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                    {"role": "user", "content": "How are you?"},
                ]

                response = client.post(
                    "/agent_response", json={"messages": messages}, headers=auth_headers
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True

                # Runner should be called with the last user message and session
                call_kwargs = mock_agent_runner.run.call_args
                assert call_kwargs.kwargs.get("input") == "How are you?"
                assert call_kwargs.kwargs.get("session") is mock_session

    def test_agent_response_endpoint_error_handling(
        self,
        client,
        auth_headers,
        mock_config,
        mock_session,
        mock_telegram_client,
    ):
        """Test error handling in agent response endpoint."""
        with patch(
            "app.core.main_router.create_orchestrator_agent"
        ) as mock_create_agent:
            mock_create_agent.side_effect = Exception("Test error")

            response = client.post(
                "/agent_response", json={"input": "Test input"}, headers=auth_headers
            )

            assert response.status_code == 500
            data = response.json()
            assert data["success"] is False
            assert "Test error" in data["message"]

            # Should still try to send error message via Telegram
            mock_telegram_client.send_message.assert_called_once()

    def test_process_alert_endpoint_success(
        self, client, auth_headers, mock_config, mock_agent_runner, mock_telegram_client
    ):
        """Test successful alert processing."""
        from app.agents.alert_processor_agent import AlertDecision

        mock_decision = AlertDecision(
            rationale="This affects commute",
            notify_user=True,
            message_content="Service disruption on Line 2.",
        )
        mock_agent_runner.run.return_value.final_output = mock_decision
        mock_agent_runner.run.return_value.last_agent = MagicMock(
            name="Alert Processor"
        )
        mock_agent_runner.run.return_value.last_agent.name = "Alert Processor"

        with patch("app.core.main_router.create_alert_processor_agent"):
            with patch("app.core.main_router.Path") as mock_path:
                with patch("app.core.main_router.open", create=True):
                    with patch("app.core.main_router.json") as mock_json:
                        mock_path.return_value.exists.return_value = False
                        mock_path.return_value.mkdir = MagicMock()
                        mock_json.dump = MagicMock()

                        alert_data = {
                            "uid": "alert_123",
                            "subject": "Test Alert",
                            "body": "Alert body",
                            "sender": "test@example.com",
                            "date": "2024-01-01T12:00:00Z",
                            "alert_type": "email",
                        }

                        response = client.post(
                            "/process_alert", json=alert_data, headers=auth_headers
                        )

                        assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["agent_processing"]["success"] is True
                    assert (
                        data["agent_processing"]["primary_agent"] == "Alert Processor"
                    )

    def test_clear_conversation_endpoint_success(
        self, client, auth_headers, mock_session
    ):
        """Test successful conversation clearing."""
        with patch("app.core.auth.config") as auth_config:
            auth_config.x_token = "12345678910"
            response = client.post("/clear_conversation", headers=auth_headers)

            assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cleared successfully" in data["message"]

        mock_session.clear_session.assert_awaited_once()

    def test_clear_conversation_endpoint_failure(self, client, auth_headers):
        """Test conversation clearing failure."""
        with patch("app.core.main_router.get_session") as mock_get_session:
            with patch("app.core.auth.config") as auth_config:
                mock_sess = MagicMock()
                mock_sess.clear_session = AsyncMock(side_effect=Exception("DB error"))
                mock_get_session.return_value = mock_sess
                auth_config.x_token = "12345678910"

                response = client.post("/clear_conversation", headers=auth_headers)

                assert response.status_code == 500
            data = response.json()
            assert data["success"] is False

    def test_authentication_required(self, client):
        """Test that endpoints require authentication."""
        endpoints = [
            ("/agent_response", {"input": "test"}),
            (
                "/process_alert",
                {
                    "uid": "test",
                    "subject": "test",
                    "body": "test",
                    "sender": "test",
                    "date": "2024-01-01T12:00:00Z",
                },
            ),
            ("/clear_conversation", None),
        ]

        for endpoint, payload in endpoints:
            if payload:
                response = client.post(endpoint, json=payload)
            else:
                response = client.post(endpoint)

            # Should require authentication (use valid token to get past auth, then check for 400/422)
            assert response.status_code in [400, 401, 403, 422]

    def test_invalid_model_request(
        self, client, auth_headers, mock_config, mock_session
    ):
        """Test request with invalid model."""
        with patch("app.core.auth.config") as auth_config:
            auth_config.x_token = "12345678910"
            response = client.post(
                "/agent_response",
                json={"input": "test", "model": "invalid-model"},
                headers=auth_headers,
            )

            # The endpoint returns 500 because it catches the HTTPException and sends error via Telegram
            assert response.status_code == 500
        data = response.json()
        assert "Invalid model" in data["message"]

    def test_missing_input_request(self, client, auth_headers, mock_config):
        """Test request without input or messages."""
        # Use a valid token to get past authentication
        with patch("app.core.auth.config") as auth_config:
            auth_config.x_token = "12345678910"
            valid_headers = {"X-Token": "12345678910"}
            response = client.post("/agent_response", json={}, headers=valid_headers)

            # The endpoint returns 422 because of Pydantic validation before our custom validation
            assert response.status_code == 422
        data = response.json()
        assert "detail" in data  # Pydantic validation error


class TestAsyncArchitectureIntegration:
    """Integration tests for the complete async architecture."""

    @pytest.mark.asyncio
    async def test_end_to_end_user_query_flow(self):
        """Test complete flow for user query processing."""
        with patch("app.core.agent_response_handler.config") as mock_config2:
            with patch("app.core.telegram_client.telegram_client") as mock_client:
                mock_config2.authorized_user_id = 12345

                mock_client.send_message = AsyncMock(return_value=(True, "msg_123"))

                # Simulate agent response with notification JSON
                agent_response = """
                <json>
                {
                    "notify_user": true,
                    "message_content": "Hello! How can I help you today?",
                    "rationale": "User greeted the bot"
                }
                </json>
                """

                from app.core.agent_response_handler import AgentResponseHandler

                (
                    should_respond,
                    message,
                ) = await AgentResponseHandler.process_user_query_response(
                    agent_response
                )

                assert should_respond is True
                assert message == "Hello! How can I help you today?"
                # Note: send_message is not called here because user queries defer to endpoint
                # The endpoint handles the actual Telegram sending

    @pytest.mark.asyncio
    async def test_end_to_end_alert_processing_flow(self):
        """Test that AlertDecision structured output works for alert processing."""
        from app.agents.alert_processor_agent import AlertDecision

        # Verify AlertDecision can be constructed and has expected fields
        decision = AlertDecision(
            rationale="This affects user's commute",
            notify_user=True,
            message_content="Service disruption on Line 2. Expect delays.",
        )

        assert decision.notify_user is True
        assert "Service disruption" in decision.message_content
        assert decision.rationale == "This affects user's commute"

        # Verify non-relevant alert decision
        skip_decision = AlertDecision(
            rationale="Elevator outage, not relevant",
            notify_user=False,
            message_content="",
        )

        assert skip_decision.notify_user is False
        assert skip_decision.message_content == ""
