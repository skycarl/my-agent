"""Shared test helpers."""

from agents.tool_context import ToolContext


def tool_context(arguments: str = "") -> ToolContext:
    """Build a ToolContext for invoking a @function_tool directly in tests.

    The Agents SDK reads tool identity off the context during invocation, so
    tools cannot be called with a bare None context.
    """
    return ToolContext(
        context=None,
        tool_name="test_tool",
        tool_call_id="test_call_id",
        tool_arguments=arguments,
    )
