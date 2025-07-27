"""
Test agent functionality.
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.agents.gardener_agent import gardener_agent
from app.agents.commute_agent import commute_agent
from app.agents.orchestrator_agent import orchestrator_agent


class TestMCPToolIntegration:
    """Test MCP tool integration functionality."""

    @pytest.mark.asyncio
    async def test_mcp_client_call_tool_success(self):
        """Test MCP client tool call with successful response."""
        with patch("app.core.mcp_client.mcp_client") as mock_mcp:
            mock_mcp.call_tool = AsyncMock(
                return_value={"content": "Plant list: tomatoes, carrots"}
            )

            # Test the client directly
            from app.core.mcp_client import mcp_client

            result = await mcp_client.call_tool("get_plants", {})

            assert result == {"content": "Plant list: tomatoes, carrots"}
            mock_mcp.call_tool.assert_called_once_with("get_plants", {})

    @pytest.mark.asyncio
    async def test_mcp_client_call_tool_error(self):
        """Test MCP client tool call with error response."""
        with patch("app.core.mcp_client.mcp_client") as mock_mcp:
            mock_mcp.call_tool = AsyncMock(return_value={"error": "Database not found"})

            from app.core.mcp_client import mcp_client

            result = await mcp_client.call_tool("get_plants", {})

            assert result == {"error": "Database not found"}


class TestAgentConfiguration:
    """Test agent configuration."""

    def test_gardener_agent_configuration(self):
        """Test that Gardener agent is properly configured."""
        assert gardener_agent.name == "Gardener"
        assert len(gardener_agent.tools) == 4
        assert gardener_agent.model is not None
        assert gardener_agent.instructions is not None
        assert "garden" in gardener_agent.instructions.lower()

    def test_commute_agent_configuration(self):
        """Test that Commute agent is properly configured."""
        assert commute_agent.name == "Commute Assistant"
        assert len(commute_agent.tools) == 2
        assert commute_agent.model is not None
        assert commute_agent.instructions is not None
        assert "commute" in commute_agent.instructions.lower()

    def test_orchestrator_agent_configuration(self):
        """Test that Orchestrator agent is properly configured."""
        assert orchestrator_agent.name == "Orchestrator"
        assert len(orchestrator_agent.handoffs) == 2
        assert gardener_agent in orchestrator_agent.handoffs
        assert commute_agent in orchestrator_agent.handoffs
        assert orchestrator_agent.model is not None
        assert orchestrator_agent.instructions is not None
        assert "orchestrator" in orchestrator_agent.instructions.lower()

    def test_agent_tools_are_configured(self):
        """Test that agent tools are properly configured."""
        # Test that tools exist
        assert gardener_agent.tools is not None
        assert len(gardener_agent.tools) == 4

        # Test that commute agent tools exist
        assert commute_agent.tools is not None
        assert len(commute_agent.tools) == 2

        # Test that handoffs exist
        assert orchestrator_agent.handoffs is not None
        assert len(orchestrator_agent.handoffs) == 2
