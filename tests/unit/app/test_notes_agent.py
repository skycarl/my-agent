"""
Test notes agent functionality.
"""

import pytest
from unittest.mock import patch

from app.agents.notes_agent import create_notes_agent


class TestNotesAgentConfiguration:
    """Test notes agent configuration."""

    def test_notes_agent_configuration(self):
        """Test that Notes agent is properly configured."""
        agent = create_notes_agent()
        assert agent.name == "Notes"
        assert len(agent.tools) == 8
        assert agent.model is not None
        assert agent.instructions is not None
        assert "obsidian" in agent.instructions.lower()

    def test_create_notes_agent_with_custom_model(self):
        """Test that create_notes_agent creates agent with specified model."""
        custom_model = "gpt-5-mini"
        agent = create_notes_agent(custom_model)
        assert agent.name == "Notes"
        assert agent.model == custom_model
        assert len(agent.tools) == 8

    def test_notes_agent_uses_sdk_defaults(self):
        """Notes agent should not have custom reasoning effort (uses SDK defaults)."""
        agent = create_notes_agent()
        assert agent.model_settings.reasoning is None


class TestNotesToolDirectCalls:
    """Test that notes tools call notes_service directly."""

    @pytest.mark.asyncio
    async def test_search_notes_tool(self):
        """Test search_notes tool calls service."""
        mock_results = [{"path": "Recipes/Pasta.md", "snippet": "...pasta recipe..."}]
        with patch(
            "app.agents.notes_agent.svc_search_notes", return_value=mock_results
        ):
            from app.agents.notes_agent import search_notes

            result = await search_notes.on_invoke_tool(
                None, '{"query": "pasta", "folder": ""}'
            )
            assert "Pasta.md" in result

    @pytest.mark.asyncio
    async def test_search_notes_no_results(self):
        """Test search_notes tool with no results."""
        with patch("app.agents.notes_agent.svc_search_notes", return_value=[]):
            from app.agents.notes_agent import search_notes

            result = await search_notes.on_invoke_tool(
                None, '{"query": "nonexistent", "folder": ""}'
            )
            assert "No notes found" in result

    @pytest.mark.asyncio
    async def test_read_note_tool(self):
        """Test read_note tool calls service."""
        with patch(
            "app.agents.notes_agent.svc_read_note",
            return_value="# Chicken Tikka\n\nDelicious recipe...",
        ):
            from app.agents.notes_agent import read_note

            result = await read_note.on_invoke_tool(
                None, '{"path": "Recipes/Chicken Tikka.md"}'
            )
            assert "Chicken Tikka" in result

    @pytest.mark.asyncio
    async def test_read_note_not_found(self):
        """Test read_note tool when note doesn't exist."""
        with patch(
            "app.agents.notes_agent.svc_read_note",
            side_effect=FileNotFoundError("Note not found"),
        ):
            from app.agents.notes_agent import read_note

            result = await read_note.on_invoke_tool(None, '{"path": "missing.md"}')
            assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_create_note_tool(self):
        """Test create_note tool calls service."""
        with patch(
            "app.agents.notes_agent.svc_write_note",
            return_value="Note saved: Test/note.md",
        ):
            from app.agents.notes_agent import create_note

            result = await create_note.on_invoke_tool(
                None, '{"path": "Test/note.md", "content": "# Hello"}'
            )
            assert "saved" in result.lower()

    @pytest.mark.asyncio
    async def test_edit_note_tool(self):
        """Test edit_note tool calls service."""
        with patch(
            "app.agents.notes_agent.svc_write_note",
            return_value="Note saved: Test/note.md",
        ):
            from app.agents.notes_agent import edit_note

            result = await edit_note.on_invoke_tool(
                None, '{"path": "Test/note.md", "content": "# Updated"}'
            )
            assert "saved" in result.lower()

    @pytest.mark.asyncio
    async def test_delete_note_tool(self):
        """Test delete_note tool calls service."""
        with patch(
            "app.agents.notes_agent.svc_delete_note",
            return_value="Note deleted: Test/note.md",
        ):
            from app.agents.notes_agent import delete_note

            result = await delete_note.on_invoke_tool(None, '{"path": "Test/note.md"}')
            assert "deleted" in result.lower()

    @pytest.mark.asyncio
    async def test_list_vault_folders_tool(self):
        """Test list_vault_folders tool calls service."""
        with patch(
            "app.agents.notes_agent.svc_list_folders",
            return_value=["Recipes", "Notes", "Journal"],
        ):
            from app.agents.notes_agent import list_vault_folders

            result = await list_vault_folders.on_invoke_tool(None, "")
            assert "Recipes" in result

    @pytest.mark.asyncio
    async def test_list_vault_notes_tool(self):
        """Test list_vault_notes tool calls service."""
        mock_notes = [
            {"path": "Recipes/Pasta.md", "size": 500, "last_modified": "2026-01-01"}
        ]
        with patch("app.agents.notes_agent.svc_list_notes", return_value=mock_notes):
            from app.agents.notes_agent import list_vault_notes

            result = await list_vault_notes.on_invoke_tool(
                None, '{"folder": "Recipes"}'
            )
            assert "Pasta.md" in result

    @pytest.mark.asyncio
    async def test_save_recipe_tool(self):
        """Test save_recipe tool fetches, parses, and saves."""
        mock_markdown = "# Chicken Tikka\n\n## Ingredients\n\n- Chicken"
        with (
            patch(
                "app.agents.notes_agent.fetch_and_parse_recipe",
                return_value=mock_markdown,
            ),
            patch(
                "app.agents.notes_agent.svc_write_note",
                return_value="Note saved: Recipes/Chicken Tikka.md",
            ),
        ):
            from app.agents.notes_agent import save_recipe

            result = await save_recipe.on_invoke_tool(
                None, '{"url": "https://example.com/recipe"}'
            )
            assert "Chicken Tikka" in result
            assert "saved" in result.lower()

    @pytest.mark.asyncio
    async def test_save_recipe_with_custom_title(self):
        """Test save_recipe tool with user-provided title."""
        mock_markdown = "# Some Recipe\n\n## Ingredients\n\n- Stuff"
        with (
            patch(
                "app.agents.notes_agent.fetch_and_parse_recipe",
                return_value=mock_markdown,
            ),
            patch(
                "app.agents.notes_agent.svc_write_note",
                return_value="Note saved: Recipes/My Recipe.md",
            ) as mock_write,
        ):
            from app.agents.notes_agent import save_recipe

            await save_recipe.on_invoke_tool(
                None, '{"url": "https://example.com/recipe", "title": "My Recipe"}'
            )
            mock_write.assert_called_once()
            assert "My Recipe" in mock_write.call_args[0][0]

    @pytest.mark.asyncio
    async def test_save_recipe_fetch_failure(self):
        """Test save_recipe tool handles fetch errors gracefully."""
        with patch(
            "app.agents.notes_agent.fetch_and_parse_recipe",
            side_effect=ValueError("Could not fetch"),
        ):
            from app.agents.notes_agent import save_recipe

            result = await save_recipe.on_invoke_tool(
                None, '{"url": "https://bad-url.com"}'
            )
            assert "Failed" in result
