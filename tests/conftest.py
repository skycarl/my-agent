"""
Shared pytest fixtures and configuration for all tests.
"""

import pytest
from unittest.mock import Mock, patch
from app.core.settings import config


@pytest.fixture
def mock_config():
    """Fixture to provide test configuration."""
    with patch.object(config, "openai_api_key", "test_key"):
        with patch.object(config, "telegram_bot_token", "test_token"):
            yield config


@pytest.fixture
def mock_openai_client():
    """Fixture to provide a mocked OpenAI client."""
    with patch("app.core.openai_client.OpenAI") as mock_client:
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_telegram_bot():
    """Fixture to provide a mocked Telegram bot."""
    with patch("telegram_bot.bot.Bot") as mock_bot:
        mock_instance = Mock()
        mock_bot.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def sample_garden_data():
    """Fixture to provide sample garden data for testing."""
    return {
        "plants": [
            {
                "id": "1",
                "name": "Tomato",
                "type": "vegetable",
                "planted_date": "2024-01-01",
                "status": "growing",
            },
            {
                "id": "2",
                "name": "Basil",
                "type": "herb",
                "planted_date": "2024-01-15",
                "status": "growing",
            },
        ]
    }
