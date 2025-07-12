<h1 align="center"> 
FastAPI Boilerplate
</h1>

<h2 align="center">
Simple FastAPI-based project template
</h2>

# 💎 Features

✅ Production ready FastAPI application\
✅ Clean architecture with clear separation of concerns\
✅ Configuration management with pydantic-settings\
✅ Async FastAPI endpoints\
✅ Loguru logging mechanism\
✅ Unit tests with Pytest\
✅ `uv` dependency management for fast and reliable builds\
✅ Telegram bot integration with OpenAI responses\
✅ Docker-compose setup for multi-service deployment


# ⚒️ Techologies Used

- Pydantic: For typing & serialization
- Pytests: For TDD or Unit Testing
- `uv`: Python dependency management packaging made easy and fast
- Docker & docker-compose: for smoother deployment
- Loguru: Easiest logging ever done
- Pydantic Settings: Type-safe environment variable management with automatic validation

# 🚀 Setup 🕙
Make sure you have docker and docker-compose installed [docker installation guide](https://docs.docker.com/compose/install/)

## Configuration
This project uses **pydantic-settings** for environment variable management for type safety and validation.

## Step 1
Create **.env** file in root folder fastapi-boilerplate/.env

The application settings are managed by `app/core/settings.py` which uses Pydantic BaseSettings for type-safe configuration.

You can use the provided `env.example` file as a template:

```
# Authentication
X_TOKEN=12345678910

# OpenAI Configuration
# Set your OpenAI API key here (leave empty if not using OpenAI services)
OPENAI_API_KEY=your-openai-api-key-here

# Telegram Bot Configuration
# Get your bot token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-here
# URL of the FastAPI app (for bot to communicate with API)
APP_URL=http://localhost:8000
```

### Available Settings:
- `X_TOKEN`: API authentication token (default: "12345678910")
- `OPENAI_API_KEY`: OpenAI API key for AI services (default: empty string)
- `TELEGRAM_BOT_TOKEN`: Telegram bot token from @BotFather (default: empty string)
- `APP_URL`: URL of the FastAPI app for internal communication (default: "http://localhost:8000")

## Step 2
```
uv sync
uv run uvicorn app.main:app --reload
```

# 🤖 Telegram Bot Integration

This project includes a Telegram bot that integrates with the FastAPI backend to provide AI-powered responses.

## Setting Up the Telegram Bot

1. **Create a Telegram Bot:**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Use `/newbot` command to create a new bot
   - Follow the instructions and get your bot token
   - Add the token to your `.env` file as `TELEGRAM_BOT_TOKEN`

2. **Configure OpenAI:**
   - Get your OpenAI API key from [OpenAI Platform](https://platform.openai.com/api-keys)
   - Add it to your `.env` file as `OPENAI_API_KEY`

## Running the Services

### Option 1: Using Docker Compose (Recommended)
```bash
# Start both API and Telegram bot services
make docker-up

# Stop services
make docker-down
```

### Option 2: Running Locally
```bash
# Terminal 1: Start the FastAPI server
make run

# Terminal 2: Start the Telegram bot
make run-bot
```

## Bot Features

- **AI-powered responses**: The bot queries the FastAPI `/responses` endpoint to generate AI responses
- **MCP Tools Integration**: Automatically includes garden management tools from the MCP server
- **Command support**: 
  - `/start` - Initialize the bot
  - `/help` - Show available commands
- **Message handling**: Send any text message to get an AI response
- **Garden Management**: Ask about plants, add new plants, record harvests, and check produce counts
- **Error handling**: Graceful error handling with user-friendly messages
- **Typing indicators**: Shows typing while processing requests

## Bot Architecture

The Telegram bot is built using:
- `python-telegram-bot` library for Telegram API integration
- Polling mode for receiving messages
- Pydantic models for type validation
- Async/await for non-blocking operations
- Comprehensive error handling and logging

## MCP Integration

The application includes a Model Context Protocol (MCP) integration that automatically makes garden management tools available to the AI assistant. The MCP server exposes tools for:

- **get_plants**: List all plants in the garden with their yields
- **add_plant**: Add a new plant to the garden
- **get_produce_counts**: Get harvest statistics for a specific plant
- **add_produce**: Record a new harvest for a plant

### MCP Configuration

The MCP integration can be configured via environment variables:

```bash
# Enable or disable MCP tools (default: true)
ENABLE_MCP_TOOLS=true

# MCP server URL (default: http://localhost:8001)
MCP_SERVER_URL=http://localhost:8001
```

### Example Usage

Ask the bot questions like:
- "What plants do I have in my garden?"
- "Add tomatoes to my garden"
- "Record a harvest of 5 pounds of tomatoes"
- "How many harvests have I recorded for peas?"

The AI will automatically use the appropriate MCP tools to answer your questions and perform actions.

# 🎉 Done!

- Swagger docs on `localhost:8000/docs`
- Interactive API documentation with simple authentication
- Telegram bot ready to chat with AI responses

# 🧹 Running Pre-commit Hooks Manually

To manually run pre-commit hooks:

1. Install the hooks defined in `.pre-commit-config.yaml`:
   ```sh
   pre-commit install
   ```
2. Run all pre-commit hooks on all files:
   ```sh
   pre-commit run --all-files
   ```

You can also run specific hooks or run them only on staged files. See the [pre-commit documentation](https://pre-commit.com/) for more options.
