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
    openai_api_key: str = Field(
        default="", description="OpenAI API key for AI services"
    )

    # Valid OpenAI models that can be used
    valid_openai_models: list[str] = Field(
        default=[
            "gpt-5",
            "gpt-5-mini",
            "o4-mini",
            "o3",
            "o3-mini",
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini",
        ],
        description="List of valid OpenAI models that can be used",
    )

    # Default model to use when no specific model is provided
    default_model: str = Field(
        default="gpt-5", description="Default OpenAI model to use for agents"
    )

    # OpenAI API timeout and retry configuration
    openai_timeout: int = Field(
        default=30, description="OpenAI API request timeout in seconds"
    )
    openai_max_retries: int = Field(
        default=3, description="Maximum number of retries for OpenAI API calls"
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    app_url: str = Field(
        default="http://localhost:8000",
        description="URL of the FastAPI app for internal communication",
    )
    authorized_user_id: int = Field(
        default=0,
        description="Authorized Telegram user ID (only this user can use the bot)",
    )
    max_conversation_history: int = Field(
        default=10,
        description="Maximum number of messages to keep in conversation history",
    )

    # MCP Configuration
    mcp_server_url: str = Field(
        default="http://localhost:8001/mcp", description="URL of the MCP server"
    )
    enable_mcp_tools: bool = Field(
        default=True, description="Enable MCP tools integration"
    )

    # Garden Database Configuration
    garden_db_path: str = Field(
        default="storage/garden_db.json",
        description="Path to the garden database JSON file",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Email Sink Configuration
    email_sink_enabled: bool = Field(
        default=False, description="Enable email sink monitoring service"
    )
    email_address: str = Field(
        default="", description="Gmail address for email monitoring"
    )
    email_password: str = Field(
        default="", description="Gmail app password for email monitoring"
    )
    email_imap_server: str = Field(
        default="imap.gmail.com", description="IMAP server for email monitoring"
    )
    email_poll_interval: int = Field(
        default=60, description="Email polling interval in seconds"
    )
    email_sender_patterns: str = Field(
        default="alerts@",
        description="Comma-separated list of sender patterns to monitor (supports substrings like 'alerts@' or '@alertdomain.com')",
    )
    storage_path: str = Field(
        default="storage", description="Path to storage directory for persistent data"
    )

    # Timezone Configuration
    timezone: str = Field(
        default="America/Los_Angeles",
        description="Application timezone (e.g., 'America/Los_Angeles', 'UTC', 'America/New_York')",
    )

    # Task Scheduler Configuration
    scheduler_enabled: bool = Field(
        default=True, description="Enable task scheduler service"
    )
    scheduler_timezone: str = Field(
        default="America/Los_Angeles", description="Timezone for scheduled tasks"
    )
    task_config_reload_interval: int = Field(
        default=30, description="Interval in seconds to check for task config changes"
    )

    # One-time (date) task behavior
    one_time_task_cleanup_mode: str = Field(
        default="remove",
        description="Cleanup strategy after a one-time task runs: 'remove' or 'disable'",
    )
    one_time_task_misfire_grace_seconds: int = Field(
        default=3600,
        description="If a one-time task was missed while the service was down, run it on next start if within this many seconds.",
    )

    @property
    def tasks_config_path(self) -> str:
        """Get the tasks configuration file path based on storage path."""
        return f"{self.storage_path}/scheduled_tasks.json"

    @property
    def task_results_path(self) -> str:
        """Get the task results file path based on storage path."""
        return f"{self.storage_path}/task_results.json"

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
        class TestConfig(cls):  # type: ignore
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
