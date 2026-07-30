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
async def test_verify_token_valid(monkeypatch):
    """Test verify_token with valid token."""
    monkeypatch.setattr(config, "x_token", "test-token")
    # This should not raise an exception
    await verify_token("test-token")


@pytest.mark.asyncio
async def test_verify_token_invalid(monkeypatch):
    """Test verify_token with invalid token."""
    monkeypatch.setattr(config, "x_token", "test-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("invalid_token")

    assert exc_info.value.status_code == 401
    assert "Invalid authentication token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_verify_token_non_ascii_rejected_cleanly(monkeypatch):
    """A non-ASCII token yields 401, not an unhandled TypeError/500.

    Starlette decodes headers as latin-1, so a client can put non-ASCII
    characters in X-Token; comparing those as str raises TypeError.
    """
    monkeypatch.setattr(config, "x_token", "test-token")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("tëst-tokèn\xff")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_token_rejects_all_when_unconfigured(monkeypatch):
    """With no X_TOKEN configured, every request is rejected (fail closed)."""
    monkeypatch.setattr(config, "x_token", "")
    with pytest.raises(HTTPException) as exc_info:
        await verify_token("")

    assert exc_info.value.status_code == 503


def test_healthcheck_endpoint():
    """Test the healthcheck endpoint."""
    response = client.get("/healthcheck")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_models_endpoint(monkeypatch):
    """Test the models endpoint with a valid token."""
    monkeypatch.setattr(config, "x_token", "test-token")
    response = client.get("/models", headers={"X-Token": "test-token"})
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    assert data["default_model"] == "gpt-5.6-terra"
    assert isinstance(data["models"], list)
    assert len(data["models"]) > 0


def test_models_endpoint_requires_token(monkeypatch):
    """The models endpoint rejects missing or invalid tokens."""
    monkeypatch.setattr(config, "x_token", "test-token")

    # Missing header -> FastAPI validation error
    assert client.get("/models").status_code == 422
    # Wrong token -> 401
    assert client.get("/models", headers={"X-Token": "wrong-token"}).status_code == 401
