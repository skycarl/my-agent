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


def test_api_endpoint_without_token():
    """Test API endpoint without proper token."""
    response = client.get("/api/sneakers")
    # Should fail due to missing or invalid token
    assert response.status_code in [422, 400]  # Depending on FastAPI validation


def test_api_endpoint_with_valid_token():
    """Test API endpoint with valid token."""
    headers = {"X-Token": config.x_token}
    response = client.get("/api/sneakers", headers=headers)
    # Should succeed with proper token
    assert response.status_code == 200
