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
    
    # OpenAI Configuration
    openai_api_key: str = Field(default="", description="OpenAI API key for AI services")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use for responses")
    
    # Telegram Bot Configuration
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    app_url: str = Field(default="http://localhost:8000", description="URL of the FastAPI app for internal communication")
    authorized_user_id: int = Field(default=0, description="Authorized Telegram user ID (only this user can use the bot)")
    max_conversation_history: int = Field(default=10, description="Maximum number of messages to keep in conversation history")
    
    # MCP Configuration
    mcp_server_url: str = Field(default="http://localhost:8001/mcp", description="URL of the MCP server")
    enable_mcp_tools: bool = Field(default=True, description="Enable MCP tools integration")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def create_test_config(cls, **kwargs) -> "Config":
        """Create a config instance for testing without loading from .env file or environment variables."""
        from pydantic_settings import PydanticBaseSettingsSource
        
        # Create a temporary class that only uses init settings (defaults + passed kwargs)
        class TestConfig(cls):
            @classmethod
            def settings_customise_sources(
                cls,
                settings_cls: type[BaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                dotenv_settings: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
            ) -> tuple[PydanticBaseSettingsSource, ...]:
                # Only use init_settings (default values + passed kwargs)
                # Exclude env_settings and dotenv_settings to avoid loading from .env or environment
                return (init_settings,)
        
        return TestConfig(**kwargs)


# Global config instance
_config = None


def get_config() -> Config:
    """Get the global config instance, creating it if it doesn't exist."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config():
    """Reset the global config instance. Used for testing."""
    global _config
    _config = None


# Create the global config instance
config = get_config()
