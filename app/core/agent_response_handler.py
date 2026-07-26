"""
Unified agent response handler with JSON parsing and notification logic.

This module provides centralized logic for processing agent responses,
including parsing JSON notification instructions from <json>...</json> tags.
Actually sending Telegram messages is the calling endpoint's responsibility.
"""

import json
import re
from typing import Dict, Optional, Tuple
from loguru import logger


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
    def _sanitize_telegram_html(text: str) -> str:
        """Sanitize text for safe Telegram HTML delivery.

        Escaping is sufficient to neutralize any markup from agent responses.
        Stripping <...> spans first would also delete ordinary prose such as
        "delay is < 10 min but > 5 min", which Telegram renders fine once
        escaped.
        """
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    async def process_agent_response(response: str) -> Tuple[str, Dict]:
        """
        Parse the notification decision from an agent response.

        Args:
            response: Raw agent response

        Returns:
            Tuple of (message_for_user, metadata). message_for_user is empty
            when the agent decided not to notify (or the decision was
            malformed); when no <json> tags are present, the original
            response is returned. Sending is the caller's responsibility.
        """
        metadata = {
            "has_json": False,
            "json_valid": False,
            "notification_decision": None,
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
            return original_response, metadata

        if parsed_json is None:
            # JSON tags found but parsing failed - return original response
            metadata["actions_taken"].append("json_parse_error")
            logger.warning(
                "JSON tags found but parsing failed, returning original response"
            )
            return original_response, metadata

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
            return original_response, metadata

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
            return "", metadata

        if not message_content.strip():
            # Agent wants to notify but provided empty message
            metadata["error"] = "Agent wants to notify but message_content is empty"
            metadata["actions_taken"].append("empty_message_content")
            logger.warning("Agent wants to notify but provided empty message_content")
            return "", metadata

        metadata["actions_taken"].append("notification_requested")
        logger.info(f"User query response ready: {message_content[:100]}...")
        return message_content, metadata

    @staticmethod
    async def process_user_query_response(
        response: str, conversation_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Process agent response for user queries.

        For user queries, we use the JSON parsing logic but handle responses differently:
        - If JSON with notify_user=true: send notification AND return message_content
        - If JSON with notify_user=false: return empty string (no response to user)
        - If no JSON: return original response

        Args:
            response: Raw agent response
            conversation_id: The conversation the response belongs to (for logging/routing)

        Returns:
            Tuple of (should_respond_to_user, message_content)
        """
        # Process through unified handler
        (
            processed_message,
            metadata,
        ) = await AgentResponseHandler.process_agent_response(response)

        # For user queries, we need to determine what to send back to the user
        if not metadata["has_json"]:
            # No JSON - return original response
            return True, response

        if not metadata["json_valid"]:
            # Malformed JSON block: return the surrounding prose but drop the
            # <json>...</json> blob, which is machine plumbing the user
            # should never see.
            stripped = re.sub(
                r"<json>.*?</json>", "", response, flags=re.DOTALL
            ).strip()
            return True, stripped or response

        # Valid JSON with notification decision
        notify_user = metadata["notification_decision"]["notify_user"]
        message_content = metadata["notification_decision"]["message_content"]

        if notify_user and message_content.strip():
            # Agent wants to notify - send the message content as response
            return True, message_content
        else:
            # Agent doesn't want to notify - no response to user
            return False, ""
