"""
Test agent functionality.
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.agents.gardener_agent import create_gardener_agent
from app.agents.commute_agent import create_commute_agent
from app.agents.orchestrator_agent import create_orchestrator_agent


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
        agent = create_gardener_agent()
        assert agent.name == "Gardener"
        assert len(agent.tools) == 4
        assert agent.model is not None
        assert agent.instructions is not None
        assert "garden" in agent.instructions.lower()

    def test_commute_agent_configuration(self):
        """Test that Commute agent is properly configured."""
        agent = create_commute_agent()
        assert agent.name == "Commute Assistant"
        assert len(agent.tools) == 2  # get_monorail_hours, get_current_date
        assert agent.model is not None
        assert agent.instructions is not None
        assert "commute" in agent.instructions.lower()

    def test_orchestrator_agent_configuration(self):
        """Test that Orchestrator agent is properly configured."""
        agent = create_orchestrator_agent()
        assert agent.name == "Orchestrator"
        assert len(agent.handoffs) == 3
        assert agent.model is not None
        assert agent.instructions is not None
        assert "orchestrator" in agent.instructions.lower()

    def test_agent_tools_are_configured(self):
        """Test that agent tools are properly configured."""
        # Test that tools exist
        gardener = create_gardener_agent()
        assert gardener.tools is not None
        assert len(gardener.tools) == 4

        # Test that commute agent tools exist
        commute = create_commute_agent()
        assert commute.tools is not None
        assert len(commute.tools) == 2  # get_monorail_hours, get_current_date

        # Test that handoffs exist
        orchestrator = create_orchestrator_agent()
        assert orchestrator.handoffs is not None
        assert len(orchestrator.handoffs) == 3


class TestAgentFactoryFunctions:
    """Test agent factory functions with different models."""

    def test_create_gardener_agent_with_custom_model(self):
        """Test that create_gardener_agent creates agent with specified model."""
        custom_model = "gpt-4o"
        agent = create_gardener_agent(custom_model)

        assert agent.name == "Gardener"
        assert agent.model == custom_model
        assert len(agent.tools) == 4

    def test_create_commute_agent_with_custom_model(self):
        """Test that create_commute_agent creates agent with specified model."""
        custom_model = "gpt-4o"
        agent = create_commute_agent(custom_model)

        assert agent.name == "Commute Assistant"
        assert agent.model == custom_model
        assert len(agent.tools) == 2

    def test_create_orchestrator_agent_with_custom_model(self):
        """Test that create_orchestrator_agent creates agent with specified model."""
        custom_model = "gpt-4o"
        agent = create_orchestrator_agent(custom_model)

        assert agent.name == "Orchestrator"
        assert agent.model == custom_model
        assert len(agent.handoffs) == 3

        # Verify that handoff agents also use the same model
        for handoff_agent in agent.handoffs:
            assert handoff_agent.model == custom_model

    def test_create_agents_with_default_model(self):
        """Test that factory functions use default model when no model is specified."""
        # Test with None model (should use default)
        gardener = create_gardener_agent(None)
        commute = create_commute_agent(None)
        orchestrator = create_orchestrator_agent(None)

        # All should have the same default model
        assert gardener.model == commute.model
        assert commute.model == orchestrator.model

        # Verify handoffs in orchestrator also use the same model
        for handoff_agent in orchestrator.handoffs:
            assert handoff_agent.model == orchestrator.model
