"""
OpenAI client helper module.

This module provides a simple interface for working with OpenAI API
using the API key from application settings.

Implements manual conversation state management using the Responses API.
"""

import json
from typing import Optional, Dict, Any, List
from openai import OpenAI
from loguru import logger
from app.core.settings import config
from app.core.mcp_client import mcp_client


class OpenAIClient:
    """OpenAI client wrapper that uses the API key from settings."""

    def __init__(self):
        """Initialize the OpenAI client."""
        self._client = None
        logger.debug("OpenAI client initialized")

        # Test API key on startup if configured
        if self.is_configured():
            self._test_api_key()

    @property
    def client(self) -> OpenAI:
        """Get the OpenAI client instance."""
        if self._client is None:
            self.validate_configuration()
            self._client = OpenAI(api_key=config.openai_api_key)
            logger.debug("OpenAI client instance created")
        return self._client

    def is_configured(self) -> bool:
        """Check if OpenAI API key is configured."""
        configured = bool(config.openai_api_key.strip())
        logger.debug(
            f"OpenAI configuration check: {'configured' if configured else 'not configured'}"
        )
        return configured

    def get_api_key(self) -> Optional[str]:
        """Get the OpenAI API key if configured."""
        return config.openai_api_key if self.is_configured() else None

    def validate_configuration(self) -> None:
        """Validate that OpenAI is properly configured."""
        if not self.is_configured():
            logger.error("OpenAI API key is not configured")
            raise ValueError(
                "OpenAI API key is not configured. "
                "Please set the OPENAI_API_KEY environment variable."
            )
        logger.debug("OpenAI configuration validated successfully")

    def _test_api_key(self) -> None:
        """Test the OpenAI API key by making a simple request."""
        try:
            logger.debug("Testing OpenAI API key validity...")
            test_client = OpenAI(api_key=config.openai_api_key)
            response = test_client.responses.create(
                model="gpt-4o-mini",
                input="This is a healthcheck. Please respond with 'OK'.",
                max_output_tokens=16,
            )
            logger.info("OpenAI API key validation successful")
            logger.debug(
                f"Test response ID: {response.id}, response: {response.output_text}"
            )
        except Exception as e:
            logger.error(f"OpenAI API key validation failed: {str(e)}")
            raise ValueError(
                f"Invalid OpenAI API key. Please check your OPENAI_API_KEY environment variable. "
                f"Error: {str(e)}"
            )

    async def create_response(
        self,
        user_input: Any,
        model: str = "gpt-4o",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a response using the OpenAI Responses API with manual conversation state.

        Args:
            user_input: The conversation history as a list of messages
            model: The model to use for the response
            tools: List of tool definitions (optional)
            tool_choice: Tool choice mode (optional)
            max_output_tokens: Max output tokens (optional)
            instructions: System instructions (optional)

        Returns:
            Dict containing the response data with updated conversation history
        """
        try:
            logger.debug(f"Calling OpenAI Responses API with model: {model}")
            logger.debug(f"User input: {user_input}")

            # Get available MCP tools if enabled and no tools provided
            if tools is None and config.enable_mcp_tools:
                try:
                    tools = await mcp_client.get_available_tools()
                    if tools:
                        logger.debug(
                            f"Retrieved {len(tools)} MCP tools for this request"
                        )
                    else:
                        logger.debug("No MCP tools available")
                except Exception as e:
                    logger.warning(f"Failed to get MCP tools: {str(e)}")
                    tools = None

            # Build the argument list for responses.create
            create_args = {
                "model": model,
                "input": user_input,
                "store": False,  # Don't store conversations on OpenAI side
            }
            if max_output_tokens is not None:
                create_args["max_output_tokens"] = max_output_tokens
            if instructions is not None:
                create_args["instructions"] = instructions
            if tools is not None:
                create_args["tools"] = tools
                logger.debug(f"Added {len(tools)} tools to OpenAI request")
            if tool_choice is not None:
                create_args["tool_choice"] = tool_choice

            response = self.client.responses.create(**create_args)

            logger.debug(
                f"OpenAI Responses API response received - ID: {response.id}, Model: {response.model}"
            )

            # Handle tool calls if present in response.output
            tool_calls = [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            tool_results = []

            if tool_calls:
                logger.debug(
                    f"Response contains {len(tool_calls)} tool calls, processing..."
                )

                # Process each tool call
                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    try:
                        tool_args = (
                            json.loads(tool_call.arguments)
                            if tool_call.arguments
                            else {}
                        )
                    except json.JSONDecodeError:
                        tool_args = {}
                    logger.debug(
                        f"Processing tool call: {tool_name} with args: {tool_args}"
                    )
                    tool_result = await mcp_client.call_tool(tool_name, tool_args)
                    tool_results.append(
                        {
                            "tool_call_id": tool_call.call_id,
                            "tool_name": tool_name,
                            "tool_result": tool_result,
                        }
                    )

                # Continue the conversation with tool results using manual conversation history
                if tool_results:
                    logger.debug(
                        "Continuing conversation with tool results using manual history"
                    )

                    conversation_history = []

                    if isinstance(user_input, list):
                        conversation_history.extend(user_input)
                    else:
                        conversation_history.append(
                            {"role": "user", "content": str(user_input)}
                        )

                    # Extract text content for the assistant message
                    assistant_text_content = ""
                    message_items = [
                        item
                        for item in response.output
                        if getattr(item, "type", None) == "message"
                    ]
                    if message_items:
                        for message_item in message_items:
                            if hasattr(message_item, "content"):
                                for content_item in message_item.content:
                                    if hasattr(content_item, "text"):
                                        assistant_text_content += content_item.text

                    if assistant_text_content:
                        conversation_history.append(
                            {"role": "assistant", "content": assistant_text_content}
                        )

                    # Add a user message with tool results to continue the conversation
                    tool_results_summary = "Tool results:\n"
                    for tool_result in tool_results:
                        tool_name = tool_result["tool_name"]
                        result_content = tool_result["tool_result"]
                        tool_results_summary += (
                            f"- {tool_name}: {json.dumps(result_content)}\n"
                        )

                    conversation_history.append(
                        {
                            "role": "user",
                            "content": f"{tool_results_summary}\nPlease provide a final response based on these tool results.",
                        }
                    )

                    # Make continuation request with full conversation history
                    continuation_args = {
                        "model": model,
                        "input": conversation_history,
                        "store": False,  # Don't store conversations on OpenAI side
                    }
                    if max_output_tokens is not None:
                        continuation_args["max_output_tokens"] = max_output_tokens
                    if instructions is not None:
                        continuation_args["instructions"] = instructions
                    if tools is not None:
                        continuation_args["tools"] = tools

                    logger.debug(
                        "Making continuation request with manual conversation history"
                    )
                    final_response = self.client.responses.create(**continuation_args)

                    # Use the final response for the result
                    response = final_response
                    logger.debug(
                        f"Continuation response received - ID: {final_response.id}"
                    )

            # Extract output_text from response.output
            output_text = ""
            message_items = [
                item
                for item in response.output
                if getattr(item, "type", None) == "message"
            ]
            if message_items:
                for message_item in message_items:
                    if hasattr(message_item, "content"):
                        for content_item in message_item.content:
                            if hasattr(content_item, "text"):
                                output_text += content_item.text

            result = {
                "id": response.id,
                "object": "response",
                "created": getattr(response, "created_at", None),
                "model": response.model,
                "output_text": output_text,
                "tool_calls": tool_calls if tool_calls else None,
                "tool_results": tool_results,
                "usage": getattr(response, "usage", None),
            }
            logger.debug("Successfully processed OpenAI Responses API response")
            return result
        except Exception as e:
            logger.info(f"OpenAI Responses API error: {str(e)}")
            logger.debug(f"Full OpenAI Responses API error details: {e}", exc_info=True)
            raise Exception(f"OpenAI Responses API error: {str(e)}")


# Create a global OpenAI client instance
openai_client = OpenAIClient()
