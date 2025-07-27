"""
Test authentication functionality
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.core.auth import verify_token
from app.core.settings import config

client = TestClient(app)


def test_config_loaded():
    """Test that config is loaded correctly."""
    assert config.x_token is not None
    assert isinstance(config.x_token, str)


@pytest.mark.asyncio
async def test_verify_token_valid():
    """Test verify_token with valid token."""
    # This should not raise an exception
    await verify_token(config.x_token)


@pytest.mark.asyncio
async def test_verify_token_invalid():
    """Test verify_token with invalid token."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("invalid_token")

    assert exc_info.value.status_code == 400
    assert "X-Token header invalid" in str(exc_info.value.detail)


def test_healthcheck_endpoint():
    """Test the healthcheck endpoint."""
    response = client.get("/healthcheck")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_models_endpoint():
    """Test the models endpoint."""
    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    assert data["default_model"] == "gpt-4o"
    assert isinstance(data["models"], list)
    assert len(data["models"]) > 0
