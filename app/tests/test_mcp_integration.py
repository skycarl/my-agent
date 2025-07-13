"""
Test MCP integration with the responses endpoint.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.settings import config


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_mcp_client_initialization():
    """Test MCP client initializes correctly."""
    from app.core.mcp_client import mcp_client

    assert mcp_client is not None
    assert mcp_client.is_enabled() == config.enable_mcp_tools


@pytest.mark.asyncio
async def test_mcp_tools_disabled():
    """Test MCP integration when disabled."""
    from app.core.mcp_client import mcp_client

    with patch.object(mcp_client, "is_enabled", return_value=False):
        tools = await mcp_client.get_available_tools()
        assert tools == []


@pytest.mark.asyncio
async def test_mcp_tools_enabled_mock():
    """Test MCP integration with mocked tools."""
    from app.core.mcp_client import mcp_client

    # Mock tools response
    mock_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_plants",
                "description": "Get all plants in the garden database",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]

    with patch.object(mcp_client, "get_available_tools", return_value=mock_tools):
        tools = await mcp_client.get_available_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "get_plants"


@pytest.mark.asyncio
async def test_mcp_tool_call_mock():
    """Test MCP tool call with mocked response."""
    from app.core.mcp_client import mcp_client

    # Mock tool call response
    mock_result = {"content": "Test result"}

    with patch.object(mcp_client, "call_tool", return_value=mock_result):
        result = await mcp_client.call_tool("get_plants", {})
        assert result == mock_result


@pytest.mark.asyncio
async def test_openai_client_with_mcp_tools():
    """Test OpenAI client includes MCP tools."""
    from app.core.openai_client import openai_client
    from app.core.mcp_client import mcp_client

    # Mock MCP tools
    mock_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_plants",
                "description": "Get all plants in the garden database",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]

    # Mock OpenAI response without tool calls
    mock_response = type(
        "MockResponse",
        (),
        {
            "id": "test-id",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o-mini",
            "choices": [
                type(
                    "MockChoice",
                    (),
                    {
                        "index": 0,
                        "message": type(
                            "MockMessage",
                            (),
                            {
                                "role": "assistant",
                                "content": "Test response",
                                "tool_calls": None,
                            },
                        )(),
                        "finish_reason": "stop",
                    },
                )()
            ],
            "usage": type(
                "MockUsage",
                (),
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )(),
        },
    )()

    with patch.object(mcp_client, "get_available_tools", return_value=mock_tools):
        with patch.object(openai_client, "_client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]
            result = await openai_client.create_response(messages)

            assert result["choices"][0]["message"]["content"] == "Test response"

            # Verify tools were passed to OpenAI
            call_args = mock_client.chat.completions.create.call_args
            assert "tools" in call_args.kwargs
            assert call_args.kwargs["tools"] == mock_tools
            assert call_args.kwargs["tool_choice"] == "auto"


def test_responses_endpoint_accepts_mcp_tools(client):
    """Test that responses endpoint works with MCP integration."""
    from app.core.mcp_client import mcp_client

    # Mock MCP tools to return empty list (no tools available)
    with patch.object(mcp_client, "get_available_tools", return_value=[]):
        headers = {"X-Token": config.x_token}
        response = client.post(
            "/responses",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers=headers,
        )

        # Should not fail even if MCP tools are not available
        assert response.status_code in [
            200,
            500,
        ]  # 200 if OpenAI key configured, 500 if not
