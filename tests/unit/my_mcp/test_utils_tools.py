"""
Unit tests for utils tools.
"""

import pytest
from unittest.mock import patch, Mock
from my_mcp.utils.tools import register_utils_tools, CurrentDateResponse
from my_mcp.utils.date_utils import get_current_date_info
from fastmcp import FastMCP


@pytest.fixture
def mock_server():
    """Create a mock FastMCP server for testing."""
    return Mock(spec=FastMCP)


def test_register_utils_tools(mock_server):
    """Test that utils tools are registered correctly."""
    # Register tools
    register_utils_tools(mock_server)

    # Verify that the tool decorator was called
    mock_server.tool.assert_called()


@patch("my_mcp.utils.tools.get_current_date_info")
def test_get_current_date_tool(mock_get_date_info):
    """Test the get_current_date tool."""
    # Mock the date info function
    mock_get_date_info.return_value = ("2024-01-15", "Monday", "14:30", "Pacific Time")

    # Create a mock server
    server = Mock(spec=FastMCP)

    # Register tools
    register_utils_tools(server)

    # Get the registered tool function
    tool_function = server.tool.call_args[0][0]

    # Call the tool
    result = tool_function()

    # Verify the result
    assert isinstance(result, CurrentDateResponse)
    assert result.current_date == "2024-01-15"
    assert result.current_day == "Monday"
    assert result.current_time == "14:30"
    assert result.timezone == "Pacific Time"

    # Verify get_current_date_info was called
    mock_get_date_info.assert_called_once()


def test_current_date_response_model():
    """Test the CurrentDateResponse model."""
    response = CurrentDateResponse(
        current_date="2024-01-15",
        current_day="Monday",
        current_time="14:30",
        timezone="Pacific Time",
    )

    assert response.current_date == "2024-01-15"
    assert response.current_day == "Monday"
    assert response.current_time == "14:30"
    assert response.timezone == "Pacific Time"


def test_get_current_date_info():
    """Test the get_current_date_info function."""
    current_date, current_day, current_time, timezone_info = get_current_date_info()

    # Verify the format of each component
    assert len(current_date) == 10  # YYYY-MM-DD format
    assert current_date.count("-") == 2

    # Verify day is a valid day of the week
    valid_days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    assert current_day in valid_days

    # Verify time format (HH:MM)
    assert len(current_time) == 5
    assert current_time.count(":") == 1

    # Verify timezone
    assert timezone_info == "Pacific Time"
