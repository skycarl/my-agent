"""
Shared pytest fixtures and configuration for all tests.
"""

import pytest
from unittest.mock import patch
from app.core.settings import config


@pytest.fixture
def mock_config():
    """Fixture to provide test configuration."""
    with patch.object(config, "openai_api_key", "test_key"):
        with patch.object(config, "telegram_bot_token", "test_token"):
            yield config
