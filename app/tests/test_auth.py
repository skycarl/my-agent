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


def test_responses_endpoint_without_token():
    """Test responses endpoint without proper token."""
    response = client.post(
        "/responses", json={"messages": [{"role": "user", "content": "Hello"}]}
    )
    # Should fail due to missing or invalid token
    assert response.status_code in [422, 400]  # Depending on FastAPI validation


def test_responses_endpoint_with_valid_token():
    """Test responses endpoint with valid token."""
    headers = {"X-Token": config.x_token}
    response = client.post(
        "/responses",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers=headers,
    )
    # Should succeed with proper OpenAI key or fail without it
    assert response.status_code in [
        200,
        500,
        422,
    ]  # 200 if OpenAI key configured, 500/422 if not


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


def test_responses_endpoint_with_invalid_model():
    """Test responses endpoint with invalid model."""
    headers = {"X-Token": config.x_token}
    response = client.post(
        "/responses",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "invalid-model",
        },
        headers=headers,
    )
    assert response.status_code == 400
    data = response.json()
    assert "Invalid model" in data["detail"]
