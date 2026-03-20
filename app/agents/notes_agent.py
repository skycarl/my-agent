"""
Notes agent for managing Obsidian vault notes via S3.

This agent handles reading, writing, searching, and organizing notes
in an Obsidian vault synced through S3. It also supports saving recipes
from URLs with automatic extraction and formatting.
"""

from agents import Agent, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from loguru import logger

from app.agents.notes.notes_service import (
    list_notes as svc_list_notes,
    read_note as svc_read_note,
    write_note as svc_write_note,
    delete_note as svc_delete_note,
    list_folders as svc_list_folders,
    search_notes as svc_search_notes,
)
from app.agents.notes.recipe_parser import fetch_and_parse_recipe
from app.core.settings import config, get_model_settings_for_agent


@function_tool
async def search_notes(query: str, folder: str = "") -> str:
    """
    Search notes by content or filename.

    Args:
        query: Text to search for (case-insensitive)
        folder: Vault folder to search in (empty for entire vault)
    """
    results = svc_search_notes(query, folder)
    if not results:
        return f"No notes found matching '{query}'"
    return str(results)


@function_tool
async def read_note(path: str) -> str:
    """
    Read a specific note from the vault.

    Args:
        path: Vault-relative path (e.g. 'Recipes/Chicken Tikka.md')
    """
    try:
        return svc_read_note(path)
    except FileNotFoundError:
        return f"Note not found: {path}"


@function_tool
async def create_note(path: str, content: str) -> str:
    """
    Create a new note in the vault.

    Args:
        path: Vault-relative path including folder (e.g. 'Recipes/Chicken Tikka.md')
        content: Markdown content for the note
    """
    return svc_write_note(path, content)


@function_tool
async def edit_note(path: str, content: str) -> str:
    """
    Replace a note's content. Always read the note first to understand its current
    content before making changes.

    Args:
        path: Vault-relative path of the note to edit
        content: The full updated markdown content
    """
    return svc_write_note(path, content)


@function_tool
async def delete_note(path: str) -> str:
    """
    Delete a note from the vault.

    Args:
        path: Vault-relative path of the note to delete
    """
    return svc_delete_note(path)


@function_tool
async def list_vault_folders() -> str:
    """List top-level folders in the vault."""
    folders = svc_list_folders()
    if not folders:
        return "No folders found in the vault"
    return str(folders)


@function_tool
async def list_vault_notes(folder: str = "") -> str:
    """
    List notes in the vault, optionally filtered by folder.

    Args:
        folder: Vault folder to list (empty for root level)
    """
    notes = svc_list_notes(folder)
    if not notes:
        return f"No notes found in '{folder}'" if folder else "No notes found in vault"
    return str(notes)


@function_tool
async def save_recipe(url: str, title: str = "", folder: str = "") -> str:
    """
    Fetch a recipe from a URL, extract its content, and save as a clean markdown note.

    Args:
        url: The recipe page URL
        title: Optional title for the note filename (auto-detected if empty)
        folder: Folder to save in (defaults to the configured recipes folder)
    """
    try:
        markdown = fetch_and_parse_recipe(url)
    except Exception as e:
        return f"Failed to fetch recipe from {url}: {e}"

    # Determine filename from title or extract from markdown
    if not title:
        first_line = markdown.split("\n", 1)[0]
        title = first_line.lstrip("# ").strip() or "Untitled Recipe"

    # Clean title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    if not safe_title:
        safe_title = "Untitled Recipe"

    save_folder = folder or config.obsidian_recipes_folder
    path = f"{save_folder}/{safe_title}.md"

    result = svc_write_note(path, markdown)
    return f"{result} — Recipe '{title}' saved to {path}"


def create_notes_agent(model: str = None) -> Agent:
    """
    Create a Notes agent for Obsidian vault management.

    Args:
        model: The OpenAI model to use for this agent

    Returns:
        Configured Notes agent
    """
    agent_model = model or config.default_model
    agent_model_settings = get_model_settings_for_agent("notes")

    notes = Agent(
        name="Notes",
        handoff_description="Manages Obsidian vault notes: reading, writing, searching, organizing notes, and saving recipes from URLs.",
        **({"model_settings": agent_model_settings} if agent_model_settings else {}),
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

You are a specialized notes management assistant. You help users manage their Obsidian vault, which is synced via S3.

Your capabilities:
- Search notes by content or filename
- Read, create, edit, and delete notes
- List folders and notes in the vault
- Save recipes from URLs (fetches, extracts, and formats as clean markdown)

Guidelines:
- When editing a note, ALWAYS read it first with `read_note` to understand the current content
- For recipes, use the `save_recipe` tool — it handles fetching, extraction, and formatting automatically
- Notes are markdown files. Use proper markdown formatting.
- File paths are relative to the vault root (e.g. 'Recipes/Chicken Tikka.md')
- Be concise and to the point. Answer the user's question directly and do not offer to continue the conversation.
""",
        tools=[
            search_notes,
            read_note,
            create_note,
            edit_note,
            delete_note,
            list_vault_folders,
            list_vault_notes,
            save_recipe,
        ],
        model=agent_model,
    )

    logger.debug(f"Notes agent created with model '{agent_model}'")
    return notes
