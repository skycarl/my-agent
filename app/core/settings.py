"""
Application config using Pydantic Settings.

This module handles all environment variable configuration using pydantic-settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application config."""

    # Authentication
    x_token: str = Field(default="12345678910", description="API authentication token")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Create a global config instance
config = Config()
