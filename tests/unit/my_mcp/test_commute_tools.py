"""
Unit tests for commute tools.
"""

import pytest
from unittest.mock import patch, Mock
from my_mcp.commute.tools import register_commute_tools, MonorailHoursResponse
from fastmcp import FastMCP


@pytest.fixture
def mock_server():
    """Create a mock FastMCP server for testing."""
    return Mock(spec=FastMCP)


def test_register_commute_tools(mock_server):
    """Test that commute tools are registered correctly."""
    # Register tools
    register_commute_tools(mock_server)

    # Verify that the tool decorator was called once (only monorail hours tool)
    assert mock_server.tool.call_count == 1


@patch("my_mcp.commute.tools.fetch_hours_rows")
def test_get_monorail_hours_success(mock_fetch_hours):
    """Test successful monorail hours retrieval with date context."""
    # Mock the fetch_hours_rows function
    mock_fetch_hours.return_value = [
        "Monday - 7:30 AM - 11:00 PM",
        "Tuesday - 7:30 AM - 11:00 PM",
        "Wednesday - 7:30 AM - 11:00 PM",
    ]

    # Create a mock server
    server = Mock(spec=FastMCP)

    # Register tools
    register_commute_tools(server)

    # Get the registered tool function
    tool_function = server.tool.call_args[0][0]

    # Call the tool
    result = tool_function()

    # Verify the result
    assert isinstance(result, MonorailHoursResponse)
    assert len(result.hours) == 3
    assert "Monday - 7:30 AM - 11:00 PM" in result.hours
    assert "Tuesday - 7:30 AM - 11:00 PM" in result.hours
    assert "Wednesday - 7:30 AM - 11:00 PM" in result.hours

    # Verify date context is included
    assert hasattr(result, "current_date")
    assert hasattr(result, "current_day")
    assert result.current_date is not None
    assert result.current_day is not None

    # Verify fetch_hours_rows was called
    mock_fetch_hours.assert_called_once()


@patch("my_mcp.commute.tools.fetch_hours_rows")
def test_get_monorail_hours_error(mock_fetch_hours):
    """Test error handling in monorail hours retrieval."""
    # Mock the fetch_hours_rows function to raise an exception
    mock_fetch_hours.side_effect = Exception("Network error")

    # Create a mock server
    server = Mock(spec=FastMCP)

    # Register tools
    register_commute_tools(server)

    # Get the registered tool function
    tool_function = server.tool.call_args[0][0]

    # Call the tool and expect an exception
    with pytest.raises(
        RuntimeError, match="Failed to fetch monorail hours: Network error"
    ):
        tool_function()


def test_monorail_hours_response_model():
    """Test the MonorailHoursResponse model."""
    hours = ["Monday - 7:30 AM - 11:00 PM", "Tuesday - 7:30 AM - 11:00 PM"]
    response = MonorailHoursResponse(
        hours=hours, current_date="2024-01-15", current_day="Monday"
    )

    assert response.hours == hours
    assert len(response.hours) == 2
    assert response.current_date == "2024-01-15"
    assert response.current_day == "Monday"
