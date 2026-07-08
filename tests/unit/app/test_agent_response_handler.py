"""
Tests for the agent response handler.
"""

import pytest
from unittest.mock import patch
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
    async def test_process_agent_response_no_json(self):
        """Test processing response without JSON."""
        response = "This is a regular response without JSON tags."

        (
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

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

        (
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        assert processed_message == "Important alert message"
        assert metadata["has_json"] is True
        assert metadata["json_valid"] is True
        assert "notification_requested" in metadata["actions_taken"]

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
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

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
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        assert processed_message == ""
        assert "empty_message_content" in metadata["actions_taken"]
        assert "empty" in metadata["error"]

    @pytest.mark.asyncio
    async def test_user_query_response_notify_true(self):
        """process_user_query_response returns the message when notify_user=true."""
        response = """
        <json>
        {
            "notify_user": true,
            "message_content": "Test response for user",
            "rationale": "Testing"
        }
        </json>
        """

        (
            should_respond,
            message,
        ) = await AgentResponseHandler.process_user_query_response(response)

        assert should_respond is True
        assert message == "Test response for user"
