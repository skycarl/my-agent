"""
OpenAI client helper module.

This module provides a simple interface for working with OpenAI API
using the API key from application settings.
"""

import json
from typing import Optional, List, Dict, Any
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
        logger.debug(f"OpenAI configuration check: {'configured' if configured else 'not configured'}")
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
            
            # Create a temporary client for testing
            test_client = OpenAI(api_key=config.openai_api_key)
            
            # Make a simple request to test the API key
            response = test_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            
            logger.info("OpenAI API key validation successful")
            logger.debug(f"Test response ID: {response.id}")
            
        except Exception as e:
            logger.error(f"OpenAI API key validation failed: {str(e)}")
            raise ValueError(
                f"Invalid OpenAI API key. Please check your OPENAI_API_KEY environment variable. "
                f"Error: {str(e)}"
            )

    async def create_response(self, messages: List[Dict[str, Any]], model: str = "gpt-4o") -> Dict[str, Any]:
        """
        Create a response using the OpenAI Responses API with MCP tools integration.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            
        Returns:
            Dict containing the response data
        """
        try:
            logger.debug(f"Calling OpenAI API with model: {model}")
            logger.debug(f"Request messages: {messages}")
            
            # Get available MCP tools
            tools = await mcp_client.get_available_tools()
            logger.debug(f"Available MCP tools: {len(tools)}")
            
            # Create initial request parameters
            request_params = {
                "model": model,
                "messages": messages  # type: ignore
            }
            
            # Add tools if available
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"
                logger.debug("Added MCP tools to OpenAI request")
            
            # Make the initial request
            response = self.client.chat.completions.create(**request_params)
            
            logger.debug(f"OpenAI API response received - ID: {response.id}, Model: {response.model}")
            
            # Check if the response contains tool calls
            if response.choices[0].message.tool_calls:
                logger.debug("Response contains tool calls, processing...")
                
                # Add the assistant's message with tool calls to the conversation
                messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        }
                        for tool_call in response.choices[0].message.tool_calls
                    ]
                })
                
                # Process each tool call
                for tool_call in response.choices[0].message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    logger.debug(f"Processing tool call: {tool_name} with args: {tool_args}")
                    
                    # Call the MCP tool
                    tool_result = await mcp_client.call_tool(tool_name, tool_args)
                    
                    # Add the tool result to the conversation
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_result),
                        "tool_call_id": tool_call.id
                    })
                
                # Make a second request to get the final response
                logger.debug("Making second request to OpenAI with tool results")
                
                final_response = self.client.chat.completions.create(
                    model=model,
                    messages=messages  # type: ignore
                )
                
                response = final_response
                logger.debug("Received final response from OpenAI")
            
            # Log token usage for monitoring
            if response.usage:
                logger.debug(f"Token usage - Prompt: {response.usage.prompt_tokens}, "
                           f"Completion: {response.usage.completion_tokens}, "
                           f"Total: {response.usage.total_tokens}")
            
            result = {
                "id": response.id,
                "object": response.object,
                "created": response.created,
                "model": response.model,
                "choices": [
                    {
                        "index": choice.index,
                        "message": {
                            "role": choice.message.role,
                            "content": choice.message.content
                        },
                        "finish_reason": choice.finish_reason
                    }
                    for choice in response.choices
                ],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else None
            }
            
            logger.debug("Successfully processed OpenAI response")
            return result
            
        except Exception as e:
            logger.info(f"OpenAI API error: {str(e)}")
            logger.debug(f"Full OpenAI API error details: {e}", exc_info=True)
            raise Exception(f"OpenAI API error: {str(e)}")


# Create a global OpenAI client instance
openai_client = OpenAIClient() 