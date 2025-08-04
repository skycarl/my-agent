"""
Unified agent response handler with JSON parsing and notification logic.

This module provides centralized logic for processing agent responses,
including parsing JSON notification instructions and handling Telegram
notifications consistently across all endpoints.
"""

import json
import re
from typing import Dict, Optional, Tuple
from loguru import logger
from app.core.conversation_manager import get_conversation_manager
from app.core.settings import config


class AgentResponseHandler:
    """Handles agent responses with unified JSON parsing and notification logic."""

    @staticmethod
    def extract_json_from_response(response: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Extract JSON from <json>...</json> tags in agent response.

        Args:
            response: Raw agent response string

        Returns:
            Tuple of (has_json_tags, parsed_json_or_none, original_response)
        """
        # Look for JSON tags
        json_pattern = r"<json>(.*?)</json>"
        match = re.search(json_pattern, response, re.DOTALL)

        if not match:
            return False, None, response

        json_content = match.group(1).strip()

        try:
            parsed_json = json.loads(json_content)
            return True, parsed_json, response
        except json.JSONDecodeError as e:
            logger.warning(f"Found JSON tags but failed to parse JSON content: {e}")
            logger.warning(f"JSON content was: {json_content}")
            return True, None, response

    @staticmethod
    def validate_notification_json(parsed_json: Dict) -> Tuple[bool, str]:
        """
        Validate that JSON contains required notification fields.

        Args:
            parsed_json: Parsed JSON dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["notify_user", "message_content", "rationale"]

        for field in required_fields:
            if field not in parsed_json:
                return False, f"Missing required field: {field}"

        # Validate types
        if not isinstance(parsed_json["notify_user"], bool):
            return False, "notify_user must be a boolean"

        if not isinstance(parsed_json["message_content"], str):
            return False, "message_content must be a string"

        if not isinstance(parsed_json["rationale"], str):
            return False, "rationale must be a string"

        return True, ""

    @staticmethod
    async def send_telegram_notification(message: str) -> Tuple[bool, Optional[str]]:
        """
        Send a notification via Telegram.

        Args:
            message: Message content to send

        Returns:
            Tuple of (success, message_id_or_error)
        """
        try:
            # Import here to avoid circular imports
            from app.core.telegram_client import telegram_client

            target_user_id = config.authorized_user_id
            if not target_user_id:
                logger.warning("No authorized user ID configured for notifications")
                return False, "No authorized user configured"

            success, message_id = await telegram_client.send_message(
                user_id=target_user_id,
                message=message,
                parse_mode="HTML",
            )

            if success:
                logger.info(
                    f"Successfully sent Telegram notification to user {target_user_id}"
                )
                return True, message_id
            else:
                logger.warning(
                    f"Failed to send Telegram notification to user {target_user_id}"
                )
                return False, "Telegram send failed"

        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False, str(e)

    @staticmethod
    async def process_agent_response(
        response: str, context: str = "user_query", alert_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict]:
        """
        Process agent response with unified JSON parsing and notification logic.

        Args:
            response: Raw agent response
            context: Context of the request ("user_query", "alert_processing")
            alert_id: Optional alert ID for tracking

        Returns:
            Tuple of (notification_sent, processed_message, metadata)
        """
        metadata = {
            "has_json": False,
            "json_valid": False,
            "notification_decision": None,
            "notification_sent": False,
            "error": None,
            "actions_taken": [],
        }

        # Extract JSON from response
        has_json, parsed_json, original_response = (
            AgentResponseHandler.extract_json_from_response(response)
        )
        metadata["has_json"] = has_json

        if not has_json:
            # No JSON tags found - return original response
            metadata["actions_taken"].append("no_json_found")
            logger.debug(
                "No JSON tags found in agent response, returning original response"
            )
            return False, original_response, metadata

        if parsed_json is None:
            # JSON tags found but parsing failed - return original response
            metadata["actions_taken"].append("json_parse_error")
            logger.warning(
                "JSON tags found but parsing failed, returning original response"
            )
            return False, original_response, metadata

        # Validate JSON structure
        is_valid, validation_error = AgentResponseHandler.validate_notification_json(
            parsed_json
        )
        metadata["json_valid"] = is_valid

        if not is_valid:
            metadata["error"] = f"Invalid JSON structure: {validation_error}"
            metadata["actions_taken"].append("json_validation_error")
            logger.warning(
                f"Invalid JSON structure in agent response: {validation_error}"
            )
            return False, original_response, metadata

        # Extract notification decision
        notify_user = parsed_json["notify_user"]
        message_content = parsed_json["message_content"]
        rationale = parsed_json["rationale"]

        metadata["notification_decision"] = {
            "notify_user": notify_user,
            "message_content": message_content,
            "rationale": rationale,
        }

        logger.info(
            f"Agent notification decision: notify_user={notify_user}, rationale: {rationale}"
        )

        if not notify_user:
            # Agent decided not to notify user
            metadata["actions_taken"].append("notification_not_needed")
            logger.info(f"Agent determined no notification needed: {rationale}")
            return False, "", metadata

        if not message_content.strip():
            # Agent wants to notify but provided empty message
            metadata["error"] = "Agent wants to notify but message_content is empty"
            metadata["actions_taken"].append("empty_message_content")
            logger.warning("Agent wants to notify but provided empty message_content")
            return False, "", metadata

        # For alert processing, send notification; for user queries, just return the message
        if context == "alert_processing":
            # Send notification
            (
                notification_sent,
                send_result,
            ) = await AgentResponseHandler.send_telegram_notification(message_content)
            metadata["notification_sent"] = notification_sent

            if notification_sent:
                metadata["actions_taken"].append("notification_sent")
                metadata["telegram_message_id"] = send_result

                # Add message to conversation history for alert processing
                conversation_manager = get_conversation_manager()
                conversation_manager.add_message(
                    role="assistant",
                    content=message_content,
                    message_type="alert",
                    alert_id=alert_id,
                )
                metadata["actions_taken"].append("added_to_conversation_history")

                return True, message_content, metadata
            else:
                metadata["actions_taken"].append("notification_failed")
                metadata["error"] = f"Failed to send notification: {send_result}"
                logger.error(f"Failed to send Telegram notification: {send_result}")
                return False, message_content, metadata
        else:
            # For user queries, don't send notification here - let the main endpoint handle it
            metadata["actions_taken"].append("notification_deferred_to_endpoint")
            metadata["notification_sent"] = False
            logger.info(f"User query response ready: {message_content[:100]}...")
            return False, message_content, metadata

    @staticmethod
    async def process_user_query_response(
        response: str, user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Process agent response for user queries.

        For user queries, we use the JSON parsing logic but handle responses differently:
        - If JSON with notify_user=true: send notification AND return message_content
        - If JSON with notify_user=false: return empty string (no response to user)
        - If no JSON: return original response

        Args:
            response: Raw agent response
            user_id: User ID for conversation history

        Returns:
            Tuple of (should_respond_to_user, message_content)
        """
        # Process through unified handler
        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(
            response=response, context="user_query"
        )

        # For user queries, we need to determine what to send back to the user
        if not metadata["has_json"]:
            # No JSON - return original response
            return True, response

        if not metadata["json_valid"]:
            # Invalid JSON - return original response
            return True, response

        # Valid JSON with notification decision
        notify_user = metadata["notification_decision"]["notify_user"]
        message_content = metadata["notification_decision"]["message_content"]

        if notify_user and message_content.strip():
            # Agent wants to notify - send the message content as response
            return True, message_content
        else:
            # Agent doesn't want to notify - no response to user
            return False, ""

    @staticmethod
    async def process_alert_response(response: str, alert_id: str) -> Dict:
        """
        Process agent response for alert processing.

        Args:
            response: Raw agent response
            alert_id: Alert ID for tracking

        Returns:
            Dict containing processing metadata
        """
        (
            notification_sent,
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(
            response=response, context="alert_processing", alert_id=alert_id
        )

        # Return comprehensive metadata for alert processing
        return {
            "success": True,
            "notification_sent": notification_sent,
            "processed_message": processed_message,
            "metadata": metadata,
            "raw_response": response,
        }
