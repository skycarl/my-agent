"""
Test recipe parser (JSON-LD extraction and LLM fallback).
"""

import json

import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from app.agents.notes.recipe_parser import (
    fetch_and_parse_recipe,
    _extract_from_json_ld,
    _find_recipe_in_json_ld,
    _format_recipe_markdown,
    _format_duration,
    _normalize_instructions,
)


class TestFormatDuration:
    """Test ISO 8601 duration formatting."""

    def test_minutes_only(self):
        assert _format_duration("PT30M") == "30 minutes"

    def test_hours_only(self):
        assert _format_duration("PT2H") == "2 hours"

    def test_hours_and_minutes(self):
        assert _format_duration("PT1H15M") == "1 hour 15 minutes"

    def test_singular_hour(self):
        assert _format_duration("PT1H") == "1 hour"

    def test_singular_minute(self):
        assert _format_duration("PT1M") == "1 minute"

    def test_empty_string(self):
        assert _format_duration("") == ""

    def test_non_iso(self):
        assert _format_duration("30 minutes") == "30 minutes"


class TestNormalizeInstructions:
    """Test instruction normalization."""

    def test_string_instructions(self):
        assert _normalize_instructions("Cook the pasta") == ["Cook the pasta"]

    def test_list_of_strings(self):
        result = _normalize_instructions(["Step 1", "Step 2"])
        assert result == ["Step 1", "Step 2"]

    def test_how_to_step_objects(self):
        steps = [
            {"@type": "HowToStep", "text": "Boil water"},
            {"@type": "HowToStep", "text": "Add pasta"},
        ]
        result = _normalize_instructions(steps)
        assert result == ["Boil water", "Add pasta"]

    def test_how_to_section_objects(self):
        sections = [
            {
                "@type": "HowToSection",
                "itemListElement": [
                    {"@type": "HowToStep", "text": "Step A"},
                    {"@type": "HowToStep", "text": "Step B"},
                ],
            }
        ]
        result = _normalize_instructions(sections)
        assert result == ["Step A", "Step B"]

    def test_filters_empty_strings(self):
        result = _normalize_instructions(["Step 1", "", "Step 2"])
        assert result == ["Step 1", "Step 2"]


class TestFindRecipeInJsonLd:
    """Test JSON-LD recipe finding."""

    def test_finds_direct_recipe(self):
        data = {"@type": "Recipe", "name": "Pasta"}
        assert _find_recipe_in_json_ld(data) == data

    def test_finds_recipe_in_graph(self):
        data = {
            "@graph": [
                {"@type": "WebPage"},
                {"@type": "Recipe", "name": "Pasta"},
            ]
        }
        result = _find_recipe_in_json_ld(data)
        assert result["name"] == "Pasta"

    def test_finds_recipe_in_list(self):
        data = [
            {"@type": "WebPage"},
            {"@type": "Recipe", "name": "Pasta"},
        ]
        result = _find_recipe_in_json_ld(data)
        assert result["name"] == "Pasta"

    def test_finds_recipe_with_type_list(self):
        data = {"@type": ["Recipe", "Thing"], "name": "Pasta"}
        result = _find_recipe_in_json_ld(data)
        assert result["name"] == "Pasta"

    def test_returns_none_when_no_recipe(self):
        data = {"@type": "WebPage", "name": "Not a recipe"}
        assert _find_recipe_in_json_ld(data) is None


class TestFormatRecipeMarkdown:
    """Test recipe markdown formatting."""

    def test_basic_recipe(self):
        recipe = {
            "name": "Pasta",
            "prepTime": "PT10M",
            "cookTime": "PT20M",
            "recipeYield": "4 servings",
            "recipeIngredient": ["200g pasta", "2 cups sauce"],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": "Boil pasta"},
                {"@type": "HowToStep", "text": "Add sauce"},
            ],
        }
        result = _format_recipe_markdown(recipe, "https://example.com")
        assert "# Pasta" in result
        assert "Source: https://example.com" in result
        assert "**Prep Time:** 10 minutes" in result
        assert "**Cook Time:** 20 minutes" in result
        assert "- 200g pasta" in result
        assert "1. Boil pasta" in result
        assert "2. Add sauce" in result

    def test_recipe_with_yield_list(self):
        recipe = {
            "name": "Test",
            "recipeYield": ["4", "4 servings"],
            "recipeIngredient": [],
            "recipeInstructions": [],
        }
        result = _format_recipe_markdown(recipe, "https://example.com")
        assert "**Servings:** 4" in result

    def test_minimal_recipe(self):
        recipe = {"name": "Simple"}
        result = _format_recipe_markdown(recipe, "https://example.com")
        assert "# Simple" in result
        assert "Source: https://example.com" in result


class TestExtractFromJsonLd:
    """Test JSON-LD extraction from HTML."""

    def test_extracts_recipe_from_script_tag(self):
        recipe_data = {
            "@type": "Recipe",
            "name": "Test Recipe",
            "recipeIngredient": ["flour", "sugar"],
            "recipeInstructions": [{"@type": "HowToStep", "text": "Mix"}],
        }
        html = f'<html><head><script type="application/ld+json">{json.dumps(recipe_data)}</script></head></html>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_from_json_ld(soup, "https://example.com")
        assert result is not None
        assert "# Test Recipe" in result
        assert "- flour" in result

    def test_returns_none_when_no_json_ld(self):
        html = "<html><head></head><body>No recipe here</body></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_from_json_ld(soup, "https://example.com") is None

    def test_handles_invalid_json(self):
        html = '<html><head><script type="application/ld+json">not valid json</script></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_from_json_ld(soup, "https://example.com") is None


class TestFetchAndParseRecipe:
    """Test the main fetch_and_parse_recipe function."""

    def test_uses_json_ld_when_available(self):
        recipe_data = {
            "@type": "Recipe",
            "name": "JSON-LD Recipe",
            "recipeIngredient": ["ingredient"],
            "recipeInstructions": [{"@type": "HowToStep", "text": "Do it"}],
        }
        html = f'<html><head><script type="application/ld+json">{json.dumps(recipe_data)}</script></head><body></body></html>'

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch(
            "app.agents.notes.recipe_parser.requests.get", return_value=mock_response
        ):
            result = fetch_and_parse_recipe("https://example.com/recipe")
            assert "# JSON-LD Recipe" in result

    def test_falls_back_to_llm(self):
        html = "<html><body><p>Some recipe content without JSON-LD</p></body></html>"
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="# LLM Extracted Recipe\n\n## Ingredients\n\n- stuff"
                )
            )
        ]

        with (
            patch(
                "app.agents.notes.recipe_parser.requests.get",
                return_value=mock_response,
            ),
            patch("app.agents.notes.recipe_parser.OpenAI") as mock_openai_cls,
        ):
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_openai_cls.return_value = mock_client

            result = fetch_and_parse_recipe("https://example.com/recipe")
            assert "LLM Extracted Recipe" in result

    def test_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")

        with patch(
            "app.agents.notes.recipe_parser.requests.get", return_value=mock_response
        ):
            with pytest.raises(Exception, match="404"):
                fetch_and_parse_recipe("https://example.com/missing")
