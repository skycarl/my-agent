"""Fetch and parse recipes from URLs into clean markdown.

Two-tier extraction:
1. JSON-LD structured data (Schema.org Recipe) — free, instant, works ~80% of sites
2. LLM fallback — sends page text to a lightweight model for extraction
"""

import json

import requests
from bs4 import BeautifulSoup
from loguru import logger
from openai import OpenAI

from app.core.settings import config

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RecipeParser/1.0)"}
_TIMEOUT = 15

_LLM_EXTRACTION_PROMPT = """Extract the recipe from this webpage text. Return ONLY clean markdown with these sections:

# [Recipe Title]

Source: {url}

**Prep Time:** [time] | **Cook Time:** [time] | **Servings:** [servings]

## Ingredients

- ingredient 1
- ingredient 2

## Instructions

1. Step one
2. Step two

## Notes

[Any relevant notes]

Rules:
- Only include the recipe content, nothing else
- If a field is not found, omit it
- Keep ingredient quantities and measurements exact
- Keep instruction steps clear and concise"""


def fetch_and_parse_recipe(url: str) -> str:
    """Fetch a recipe URL and return clean markdown.

    Tries JSON-LD extraction first, falls back to LLM extraction.

    Args:
        url: The recipe page URL.

    Returns:
        Formatted markdown string of the recipe.

    Raises:
        ValueError: If the URL can't be fetched or no recipe is found.
    """
    response = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Try JSON-LD first
    markdown = _extract_from_json_ld(soup, url)
    if markdown:
        logger.info(f"Extracted recipe from JSON-LD: {url}")
        return markdown

    # Fall back to LLM extraction
    logger.info(f"No JSON-LD recipe found, using LLM extraction: {url}")
    page_text = soup.get_text(separator="\n", strip=True)
    return _extract_via_llm(page_text, url)


def _extract_from_json_ld(soup: BeautifulSoup, url: str) -> str | None:
    """Try to extract a recipe from JSON-LD structured data.

    Returns formatted markdown if a Recipe schema is found, None otherwise.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        recipe = _find_recipe_in_json_ld(data)
        if recipe:
            return _format_recipe_markdown(recipe, url)

    return None


def _find_recipe_in_json_ld(data) -> dict | None:
    """Recursively search JSON-LD data for a Recipe type."""
    if isinstance(data, dict):
        schema_type = data.get("@type", "")
        # @type can be a string or list
        if isinstance(schema_type, list):
            types = schema_type
        else:
            types = [schema_type]

        if "Recipe" in types:
            return data

        # Check @graph
        for item in data.get("@graph", []):
            result = _find_recipe_in_json_ld(item)
            if result:
                return result

    elif isinstance(data, list):
        for item in data:
            result = _find_recipe_in_json_ld(item)
            if result:
                return result

    return None


def _format_recipe_markdown(recipe: dict, url: str) -> str:
    """Format a JSON-LD Recipe dict as clean markdown."""
    lines = []

    # Title
    title = recipe.get("name", "Untitled Recipe")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Source: {url}")
    lines.append("")

    # Time and servings
    meta_parts = []
    if prep := recipe.get("prepTime"):
        meta_parts.append(f"**Prep Time:** {_format_duration(prep)}")
    if cook := recipe.get("cookTime"):
        meta_parts.append(f"**Cook Time:** {_format_duration(cook)}")
    if total := recipe.get("totalTime"):
        meta_parts.append(f"**Total Time:** {_format_duration(total)}")
    if servings := recipe.get("recipeYield"):
        if isinstance(servings, list):
            servings = servings[0]
        meta_parts.append(f"**Servings:** {servings}")

    if meta_parts:
        lines.append(" | ".join(meta_parts))
        lines.append("")

    # Ingredients
    ingredients = recipe.get("recipeIngredient", [])
    if ingredients:
        lines.append("## Ingredients")
        lines.append("")
        for ing in ingredients:
            lines.append(f"- {ing}")
        lines.append("")

    # Instructions
    instructions = recipe.get("recipeInstructions", [])
    if instructions:
        lines.append("## Instructions")
        lines.append("")
        steps = _normalize_instructions(instructions)
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # Notes
    if notes := recipe.get("description"):
        lines.append("## Notes")
        lines.append("")
        lines.append(notes)
        lines.append("")

    return "\n".join(lines)


def _normalize_instructions(instructions) -> list[str]:
    """Normalize recipeInstructions into a flat list of step strings."""
    steps = []
    if isinstance(instructions, str):
        return [instructions]

    for item in instructions:
        if isinstance(item, str):
            steps.append(item)
        elif isinstance(item, dict):
            if item.get("@type") == "HowToStep":
                steps.append(item.get("text", ""))
            elif item.get("@type") == "HowToSection":
                # Nested sections — flatten
                for sub in item.get("itemListElement", []):
                    if isinstance(sub, dict):
                        steps.append(sub.get("text", ""))
                    elif isinstance(sub, str):
                        steps.append(sub)
    return [s for s in steps if s]


def _format_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT30M, PT1H15M) to human-readable string."""
    if not iso_duration or not iso_duration.startswith("PT"):
        return iso_duration or ""

    d = iso_duration[2:]
    parts = []
    hours = ""
    minutes = ""

    if "H" in d:
        hours, d = d.split("H", 1)
        h = int(hours)
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if "M" in d:
        minutes, d = d.split("M", 1)
        m = int(minutes)
        parts.append(f"{m} minute{'s' if m != 1 else ''}")

    return " ".join(parts) if parts else iso_duration


def _extract_via_llm(page_text: str, url: str) -> str:
    """Use a lightweight LLM to extract a recipe from raw page text."""
    # Truncate to avoid excessive token usage
    truncated = page_text[:6000]

    client = OpenAI(api_key=config.openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": _LLM_EXTRACTION_PROMPT.format(url=url),
            },
            {
                "role": "user",
                "content": f"Extract the recipe from this page:\n\n{truncated}",
            },
        ],
        temperature=0,
    )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError(f"LLM could not extract a recipe from: {url}")

    return content.strip()
