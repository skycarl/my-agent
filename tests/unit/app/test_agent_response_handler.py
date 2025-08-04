"""
Tests for the agent response handler.
"""

import pytest
from unittest.mock import patch, AsyncMock
from app.core.agent_response_handler import AgentResponseHandler


class TestAgentResponseHandler:
    """Test the AgentResponseHandler class."""

    def test_extract_json_from_response_with_valid_json(self):
        """Test extracting valid JSON from response."""
        response = """
        Here is some text before.
        <json>
        {
            "notify_user": true,
            "message_content": "Test message",
            "rationale": "Testing"
        }
        </json>
        And some text after.
        """

        has_json, parsed_json, original = (
            AgentResponseHandler.extract_json_from_response(response)
        )

        assert has_json is True
        assert parsed_json is not None
        assert parsed_json["notify_user"] is True
        assert parsed_json["message_content"] == "Test message"
        assert parsed_json["rationale"] == "Testing"
        assert original == response

    def test_extract_json_from_response_no_tags(self):
        """Test response without JSON tags."""
        response = "This is just a regular response without any JSON."

        has_json, parsed_json, original = (
            AgentResponseHandler.extract_json_from_response(response)
        )

        assert has_json is False
        assert parsed_json is None
        assert original == response

    def test_extract_json_from_response_invalid_json(self):
        """Test response with JSON tags but invalid JSON content."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Test message"
            // Invalid comment in JSON
        }
        </json>
        """

        has_json, parsed_json, original = (
            AgentResponseHandler.extract_json_from_response(response)
        )

        assert has_json is True
        assert parsed_json is None
        assert original == response

    def test_validate_notification_json_valid(self):
        """Test validation of valid notification JSON."""
        valid_json = {
            "notify_user": True,
            "message_content": "Test message",
            "rationale": "Testing validation",
        }

        is_valid, error = AgentResponseHandler.validate_notification_json(valid_json)

        assert is_valid is True
        assert error == ""

    def test_validate_notification_json_missing_fields(self):
        """Test validation with missing required fields."""
        invalid_json = {
            "notify_user": True,
            "message_content": "Test message",
            # Missing rationale
        }

        is_valid, error = AgentResponseHandler.validate_notification_json(invalid_json)

        assert is_valid is False
        assert "rationale" in error

    def test_validate_notification_json_wrong_types(self):
        """Test validation with wrong field types."""
        invalid_json = {
            "notify_user": "true",  # Should be boolean
            "message_content": "Test message",
            "rationale": "Testing",
        }

        is_valid, error = AgentResponseHandler.validate_notification_json(invalid_json)

        assert is_valid is False
        assert "boolean" in error

    @pytest.mark.asyncio
    async def test_send_telegram_notification_success(self):
        """Test successful Telegram notification."""
        with patch("app.core.telegram_client.telegram_client") as mock_client:
            with patch("app.core.agent_response_handler.config") as mock_config:
                mock_config.authorized_user_id = 12345
                mock_client.send_message = AsyncMock(return_value=(True, "msg_123"))

                success, result = await AgentResponseHandler.send_telegram_notification(
                    "Test message"
                )

                assert success is True
                assert result == "msg_123"
                mock_client.send_message.assert_called_once_with(
                    user_id=12345, message="Test message", parse_mode="HTML"
                )

    @pytest.mark.asyncio
    async def test_send_telegram_notification_no_user_id(self):
        """Test Telegram notification with no authorized user."""
        with patch("app.core.agent_response_handler.config") as mock_config:
            mock_config.authorized_user_id = None

            success, result = await AgentResponseHandler.send_telegram_notification(
                "Test message"
            )

            assert success is False
            assert "No authorized user configured" in result

    @pytest.mark.asyncio
    async def test_send_telegram_notification_failure(self):
        """Test failed Telegram notification."""
        with patch("app.core.telegram_client.telegram_client") as mock_client:
            with patch("app.core.agent_response_handler.config") as mock_config:
                mock_config.authorized_user_id = 12345
                mock_client.send_message = AsyncMock(return_value=(False, None))

                success, result = await AgentResponseHandler.send_telegram_notification(
                    "Test message"
                )

                assert success is False
                assert "Telegram send failed" in result

    @pytest.mark.asyncio
    async def test_process_agent_response_no_json(self):
        """Test processing response without JSON."""
        response = "This is a regular response without JSON tags."

        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        assert notification_sent is False
        assert processed_message == response
        assert metadata["has_json"] is False
        assert "no_json_found" in metadata["actions_taken"]

    @pytest.mark.asyncio
    async def test_process_agent_response_valid_notification(self):
        """Test processing response with valid notification JSON."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Important alert message",
            "rationale": "User needs to be notified"
        }
        </json>
        """

        with patch.object(
            AgentResponseHandler, "send_telegram_notification"
        ) as mock_send:
            with patch(
                "app.core.agent_response_handler.get_conversation_manager"
            ) as mock_cm:
                mock_send.return_value = (True, "msg_123")
                mock_cm.return_value.add_message.return_value = True

                (
                    notification_sent,
                    processed_message,
                    metadata,
                ) = await AgentResponseHandler.process_agent_response(
                    response, context="alert_processing", alert_id="alert_456"
                )

                assert notification_sent is True
                assert processed_message == "Important alert message"
                assert metadata["has_json"] is True
                assert metadata["json_valid"] is True
                assert metadata["notification_sent"] is True
                assert "notification_sent" in metadata["actions_taken"]

    @pytest.mark.asyncio
    async def test_process_agent_response_no_notification_needed(self):
        """Test processing response where agent decides not to notify."""
        response = """
        <json>
        {
            "notify_user": false,
            "message_content": "",
            "rationale": "This alert is not relevant to the user"
        }
        </json>
        """

        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        assert notification_sent is False
        assert processed_message == ""
        assert metadata["notification_decision"]["notify_user"] is False
        assert "notification_not_needed" in metadata["actions_taken"]

    @pytest.mark.asyncio
    async def test_process_user_query_response_with_notification(self):
        """Test processing user query response with notification."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Here's your answer",
            "rationale": "User asked a question"
        }
        </json>
        """

        with patch.object(
            AgentResponseHandler, "process_agent_response"
        ) as mock_process:
            mock_process.return_value = (
                True,
                "Here's your answer",
                {
                    "has_json": True,
                    "json_valid": True,
                    "notification_decision": {
                        "notify_user": True,
                        "message_content": "Here's your answer",
                    },
                },
            )

            (
                should_respond,
                message,
            ) = await AgentResponseHandler.process_user_query_response(response)

            assert should_respond is True
            assert message == "Here's your answer"

    @pytest.mark.asyncio
    async def test_process_user_query_response_no_json(self):
        """Test processing user query response without JSON."""
        response = "Regular response without JSON."

        with patch.object(
            AgentResponseHandler, "process_agent_response"
        ) as mock_process:
            mock_process.return_value = (
                False,
                response,
                {"has_json": False, "json_valid": False},
            )

            (
                should_respond,
                message,
            ) = await AgentResponseHandler.process_user_query_response(response)

            assert should_respond is True
            assert message == response

    @pytest.mark.asyncio
    async def test_process_alert_response(self):
        """Test processing alert response."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Alert processed",
            "rationale": "Important alert"
        }
        </json>
        """

        with patch.object(
            AgentResponseHandler, "process_agent_response"
        ) as mock_process:
            mock_process.return_value = (
                True,
                "Alert processed",
                {"has_json": True, "notification_sent": True},
            )

            result = await AgentResponseHandler.process_alert_response(
                response, "alert_123"
            )

            assert result["success"] is True
            assert result["notification_sent"] is True
            assert result["processed_message"] == "Alert processed"
            assert result["raw_response"] == response
            mock_process.assert_called_once_with(
                response=response, context="alert_processing", alert_id="alert_123"
            )

    @pytest.mark.asyncio
    async def test_process_alert_response_no_json(self):
        """Test processing alert response when agent returns regular text (no JSON)."""
        response = (
            "I've reviewed the alert but it doesn't seem relevant for notifications."
        )

        with patch.object(
            AgentResponseHandler, "process_agent_response"
        ) as mock_process:
            mock_process.return_value = (
                False,
                response,
                {
                    "has_json": False,
                    "notification_sent": False,
                    "actions_taken": ["no_json_found"],
                },
            )

            result = await AgentResponseHandler.process_alert_response(
                response, "alert_456"
            )

            assert result["success"] is True
            assert result["notification_sent"] is False
            assert result["processed_message"] == response
            assert result["metadata"]["has_json"] is False
            assert result["raw_response"] == response
            mock_process.assert_called_once_with(
                response=response, context="alert_processing", alert_id="alert_456"
            )

    @pytest.mark.asyncio
    async def test_process_agent_response_telegram_error(self):
        """Test processing when Telegram sending fails during alert processing."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Test message",
            "rationale": "Testing error handling"
        }
        </json>
        """

        with patch.object(
            AgentResponseHandler, "send_telegram_notification"
        ) as mock_send:
            mock_send.return_value = (False, "Connection error")

            (
                notification_sent,
                processed_message,
                metadata,
            ) = await AgentResponseHandler.process_agent_response(
                response, context="alert_processing", alert_id="test_alert"
            )

            assert notification_sent is False
            assert processed_message == "Test message"
            assert metadata["notification_sent"] is False
            assert "notification_failed" in metadata["actions_taken"]
            assert "Connection error" in metadata["error"]

    @pytest.mark.asyncio
    async def test_process_agent_response_empty_message_content(self):
        """Test processing when agent wants to notify but provides empty message."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "",
            "rationale": "Testing empty message"
        }
        </json>
        """

        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        assert notification_sent is False
        assert processed_message == ""
        assert "empty_message_content" in metadata["actions_taken"]
        assert "empty" in metadata["error"]

    @pytest.mark.asyncio
    async def test_user_query_no_duplicate_notifications(self):
        """Test that user queries don't send duplicate Telegram notifications."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Test response for user",
            "rationale": "Testing no duplication"
        }
        </json>
        """

        # For user queries, process_agent_response should NOT send Telegram notification
        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(
            response, context="user_query"
        )

        # Should NOT have sent notification (deferred to endpoint)
        assert notification_sent is False
        assert processed_message == "Test response for user"
        assert metadata["notification_sent"] is False
        assert "notification_deferred_to_endpoint" in metadata["actions_taken"]

        # But process_user_query_response should still return should_respond=True
        (
            should_respond,
            message,
        ) = await AgentResponseHandler.process_user_query_response(response)

        assert should_respond is True
        assert message == "Test response for user"
