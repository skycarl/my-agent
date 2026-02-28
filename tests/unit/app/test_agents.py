"""
Test agent functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app.agents.alert_processor_agent import (
    AlertDecision,
    create_alert_processor_agent,
)
from app.agents.gardener_agent import create_gardener_agent
from app.agents.commute_agent import create_commute_agent
from app.agents.orchestrator_agent import create_orchestrator_agent


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
        assert len(agent.tools) == 8
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
        assert len(commute.tools) == 8

        # Test that handoffs exist
        orchestrator = create_orchestrator_agent()
        assert orchestrator.handoffs is not None
        assert len(orchestrator.handoffs) == 3


class TestAgentFactoryFunctions:
    """Test agent factory functions with different models."""

    def test_create_gardener_agent_with_custom_model(self):
        """Test that create_gardener_agent creates agent with specified model."""
        custom_model = "gpt-5-mini"
        agent = create_gardener_agent(custom_model)

        assert agent.name == "Gardener"
        assert agent.model == custom_model
        assert len(agent.tools) == 4

    def test_create_commute_agent_with_custom_model(self):
        """Test that create_commute_agent creates agent with specified model."""
        custom_model = "gpt-5-mini"
        agent = create_commute_agent(custom_model)

        assert agent.name == "Commute Assistant"
        assert agent.model == custom_model
        assert len(agent.tools) == 8

    def test_create_orchestrator_agent_with_custom_model(self):
        """Test that create_orchestrator_agent creates agent with specified model."""
        custom_model = "gpt-5-mini"
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


class TestGardenToolDirectCalls:
    """Test that gardener tools call garden_service directly."""

    @pytest.mark.asyncio
    async def test_get_plants_tool(self):
        """Test get_plants tool returns garden data."""
        mock_plants = {"plants": {"tomatoes": MagicMock()}}
        with patch(
            "app.agents.gardener_agent.svc_get_plants", return_value=mock_plants
        ):
            from app.agents.gardener_agent import get_plants

            result = await get_plants.on_invoke_tool(None, "")
            assert "plants" in result

    @pytest.mark.asyncio
    async def test_add_plant_tool(self):
        """Test add_plant tool calls service."""
        with patch(
            "app.agents.gardener_agent.svc_add_plant",
            return_value={"message": "Plant 'basil' added successfully"},
        ):
            from app.agents.gardener_agent import add_plant

            result = await add_plant.on_invoke_tool(None, '{"plant_name": "basil"}')
            assert "added successfully" in result

    @pytest.mark.asyncio
    async def test_get_produce_counts_tool(self):
        """Test get_produce_counts tool calls service."""
        from app.agents.gardener.garden_service import ProduceCountsResponse

        mock_response = ProduceCountsResponse(
            plant_name="tomatoes", total_yield=Decimal("10"), harvest_count=3
        )
        with patch(
            "app.agents.gardener_agent.svc_get_produce_counts",
            return_value=mock_response,
        ):
            from app.agents.gardener_agent import get_produce_counts

            result = await get_produce_counts.on_invoke_tool(
                None, '{"plant_name": "tomatoes"}'
            )
            assert "tomatoes" in result

    @pytest.mark.asyncio
    async def test_add_produce_tool(self):
        """Test add_produce tool calls service."""
        with patch(
            "app.agents.gardener_agent.svc_add_produce",
            return_value={"message": "Added 5 to tomatoes. Total yield is now 15"},
        ):
            from app.agents.gardener_agent import add_produce

            result = await add_produce.on_invoke_tool(
                None,
                '{"plant_name": "tomatoes", "amount": 5.0, "notes": ""}',
            )
            assert "Added 5" in result


class TestCommuteToolDirectCalls:
    """Test that commute tools call commute_service directly."""

    @pytest.mark.asyncio
    async def test_get_current_date_tool(self):
        """Test get_current_date tool returns date info."""
        from app.agents.commute_agent import get_current_date

        result = await get_current_date.on_invoke_tool(None, "")
        assert "current_date" in result
        assert "current_day" in result
        assert "current_time" in result

    @pytest.mark.asyncio
    async def test_get_recent_alerts_tool(self):
        """Test get_recent_alerts tool calls service."""
        from app.agents.commute.commute_service import RecentAlertsResponse

        mock_response = RecentAlertsResponse(alerts=[], total_stored=0)
        with patch(
            "app.agents.commute_agent.svc_get_recent_alerts",
            return_value=mock_response,
        ):
            from app.agents.commute_agent import get_recent_alerts

            result = await get_recent_alerts.on_invoke_tool(None, '{"limit": 5}')
            assert "alerts" in result

    @pytest.mark.asyncio
    async def test_read_commute_preferences_tool(self):
        """Test read_commute_preferences tool calls service."""
        with patch(
            "app.agents.commute_agent.svc_read_preferences_file",
            return_value="# Commute Preferences\n",
        ):
            from app.agents.commute_agent import read_commute_preferences

            result = await read_commute_preferences.on_invoke_tool(None, "")
            assert "Commute Preferences" in result

    @pytest.mark.asyncio
    async def test_write_commute_preferences_tool(self):
        """Test write_commute_preferences tool calls service."""
        with patch(
            "app.agents.commute_agent.svc_write_preferences_file",
            return_value="Commute preferences updated successfully.",
        ):
            from app.agents.commute_agent import write_commute_preferences

            result = await write_commute_preferences.on_invoke_tool(
                None, '{"content": "# Updated"}'
            )
            assert "updated successfully" in result

    @pytest.mark.asyncio
    async def test_get_commute_overrides_tool(self):
        """Test get_commute_overrides_tool calls service."""
        with patch(
            "app.agents.commute_agent.svc_get_commute_overrides",
            return_value=[],
        ):
            from app.agents.commute_agent import get_commute_overrides_tool

            result = await get_commute_overrides_tool.on_invoke_tool(None, "")
            assert "[]" in result

    @pytest.mark.asyncio
    async def test_add_commute_override_tool(self):
        """Test add_commute_override_tool calls service."""
        mock_entry = {
            "id": "abc12345",
            "date": "2026-03-01",
            "type": "commute_day",
            "note": "going in for a meeting",
            "expires_after": "2026-03-01",
        }
        with patch(
            "app.agents.commute_agent.svc_add_commute_override",
            return_value=mock_entry,
        ):
            from app.agents.commute_agent import add_commute_override_tool

            result = await add_commute_override_tool.on_invoke_tool(
                None,
                '{"date": "2026-03-01", "override_type": "commute_day", "note": "going in for a meeting"}',
            )
            assert "abc12345" in result

    @pytest.mark.asyncio
    async def test_remove_commute_override_tool(self):
        """Test remove_commute_override_tool calls service."""
        with patch(
            "app.agents.commute_agent.svc_remove_commute_override",
            return_value=True,
        ):
            from app.agents.commute_agent import remove_commute_override_tool

            result = await remove_commute_override_tool.on_invoke_tool(
                None, '{"override_id": "abc12345"}'
            )
            assert "removed" in result


class TestAlertProcessorAgentConfiguration:
    """Test alert processor agent configuration."""

    def test_alert_processor_agent_configuration(self):
        """Test that Alert Processor agent is properly configured."""
        agent = create_alert_processor_agent()
        assert agent.name == "Alert Processor"
        assert agent.output_type is not None
        assert agent.output_type is AlertDecision
        assert len(agent.tools) == 2  # get_current_date, get_recent_alerts
        assert agent.model is not None

    def test_create_alert_processor_with_custom_model(self):
        """Test that create_alert_processor_agent creates agent with specified model."""
        agent = create_alert_processor_agent("gpt-5-mini")
        assert agent.model == "gpt-5-mini"
        assert agent.output_type is AlertDecision

    def test_create_alert_processor_without_commute_context(self):
        """Test that alert processor works without commute context."""
        agent = create_alert_processor_agent()
        assert "Schedule-Aware Filtering" not in agent.instructions

    def test_create_alert_processor_with_commute_context(self):
        """Test that alert processor includes schedule context when provided."""
        context = "Today is Thursday, 2026-02-28.\n### Commute Preferences\n- Thursday: Office"
        agent = create_alert_processor_agent(commute_context=context)
        assert "User Commute Context" in agent.instructions
        assert "Schedule-Aware Filtering" in agent.instructions
        assert "Thursday: Office" in agent.instructions
