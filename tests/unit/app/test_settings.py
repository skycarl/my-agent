"""
Test settings configuration and environment variable loading.
"""

import os
from unittest.mock import patch

from app.core.settings import Config


def test_config_defaults():
    """Test that config has proper default values."""
    # Use the test config method that doesn't load from .env file
    config = Config.create_test_config()

    # Test authentication token default
    assert config.x_token == "12345678910"

    # Test OpenAI API key default (should be empty string)
    assert config.openai_api_key == ""

    # Test valid OpenAI models default
    expected_models = [
        "gpt-5",
        "gpt-5-mini",
        "o4-mini",
        "o3",
        "o3-mini",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini",
    ]
    assert config.valid_openai_models == expected_models

    # Test default model
    assert config.default_model == "gpt-5"

    # Test Telegram bot token default
    assert config.telegram_bot_token == ""

    # Test App URL default
    assert config.app_url == "http://localhost:8000"

    # Verify all fields are strings
    assert isinstance(config.openai_api_key, str)


def test_config_from_env_vars():
    """Test that config properly loads from environment variables."""
    # Test with environment variables set
    env_vars = {"X_TOKEN": "custom_token_123", "OPENAI_API_KEY": "sk-test-key-12345"}

    with patch.dict(os.environ, env_vars):
        config = Config()

        assert config.x_token == "custom_token_123"
        assert config.openai_api_key == "sk-test-key-12345"


def test_config_case_insensitive():
    """Test that config is case insensitive for environment variables."""
    # Test with lowercase environment variables
    env_vars = {"x_token": "lowercase_token", "openai_api_key": "sk-lowercase-key"}

    with patch.dict(os.environ, env_vars):
        config = Config()

        assert config.x_token == "lowercase_token"
        assert config.openai_api_key == "sk-lowercase-key"


def test_config_partial_env_override():
    """Test that only specified environment variables are overridden."""
    env_vars = {"OPENAI_API_KEY": "sk-only-openai-key"}

    with patch.dict(os.environ, env_vars):
        config = Config()

        # x_token should use default
        assert config.x_token == "123"
        # openai_api_key should use env var
        assert config.openai_api_key == "sk-only-openai-key"


def test_config_empty_env_vars():
    """Test that empty environment variables are handled correctly."""
    env_vars = {"X_TOKEN": "", "OPENAI_API_KEY": ""}

    with patch.dict(os.environ, env_vars):
        config = Config()

        assert config.x_token == ""
        assert config.openai_api_key == ""


def test_config_singleton_behavior():
    """Test that config behaves consistently when imported multiple times."""
    from app.core.settings import config as config1
    from app.core.settings import config as config2

    # Both should be the same instance
    assert config1 is config2
    assert config1.x_token == config2.x_token
    assert config1.openai_api_key == config2.openai_api_key
