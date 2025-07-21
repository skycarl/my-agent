"""
Test OpenAI client functionality.
"""

import pytest
from unittest.mock import patch

from app.core.openai_client import OpenAIClient
from app.core.settings import Config


def test_openai_client_not_configured():
    """Test OpenAI client when API key is not configured."""
    # Test with empty API key
    config = Config(openai_api_key="")

    with patch("app.core.openai_client.config", config):
        with patch.object(OpenAIClient, "_test_api_key", return_value=None):
            client = OpenAIClient()

        assert not client.is_configured()
        assert client.get_api_key() is None

        with pytest.raises(ValueError, match="OpenAI API key is not configured"):
            client.validate_configuration()


def test_openai_client_configured():
    """Test OpenAI client when API key is configured."""
    test_key = "sk-test-key-12345"
    config = Config(openai_api_key=test_key)

    with patch("app.core.openai_client.config", config):
        with patch.object(OpenAIClient, "_test_api_key", return_value=None):
            client = OpenAIClient()

        assert client.is_configured()
        assert client.get_api_key() == test_key

        # Should not raise an exception
        client.validate_configuration()


def test_openai_client_whitespace_key():
    """Test OpenAI client with whitespace-only API key."""
    config = Config(openai_api_key="   ")

    with patch("app.core.openai_client.config", config):
        with patch.object(OpenAIClient, "_test_api_key", return_value=None):
            client = OpenAIClient()

        assert not client.is_configured()
        assert client.get_api_key() is None

        with pytest.raises(ValueError, match="OpenAI API key is not configured"):
            client.validate_configuration()


def test_openai_client_with_key_containing_spaces():
    """Test OpenAI client with API key that has leading/trailing spaces."""
    test_key = "  sk-test-key-12345  "
    config = Config(openai_api_key=test_key)

    with patch("app.core.openai_client.config", config):
        with patch.object(OpenAIClient, "_test_api_key", return_value=None):
            client = OpenAIClient()

        # Should still be configured because we have non-whitespace content
        assert client.is_configured()
        assert client.get_api_key() == test_key

        # Should not raise an exception
        client.validate_configuration()
