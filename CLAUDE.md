# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal AI assistant built with the OpenAI Agents SDK, FastAPI, and a Telegram bot interface. The system uses an orchestrator pattern where an Orchestrator agent routes user requests to specialized agents (Gardener, Commute, Scheduler) via handoffs.

## Common Commands

```bash
make install          # Install dependencies (uv sync)
make run              # Start FastAPI server with reload
make run-bot          # Start Telegram bot
make run-mcp          # Start MCP server
make test             # Run all tests
make test-unit        # Run unit tests only
make test-app         # Run app service unit tests
make test-mcp         # Run MCP service unit tests
make test-telegram    # Run telegram bot unit tests
make lint             # Run ruff format + ruff check
make docker-up        # Build and start all services
make docker-down      # Stop all services
make logs             # Tail docker compose logs

# Run a single test file
uv run pytest tests/unit/app/test_agents.py -v

# Run a specific test
uv run pytest tests/unit/app/test_agents.py::test_name -v
```

## Architecture

### Four Docker Services (`docker-compose.yml`)

1. **app** (port 8001) — FastAPI backend. Entry point: `app/main.py`. Routes in `app/core/main_router.py`. Starts the APScheduler-based scheduler on startup via lifespan hook.
2. **telegram-bot** — Telegram bot that sends user messages to the app's `/agent_response` endpoint. Entry point: `telegram_bot/main.py`.
3. **mcp-server** (port 8002) — FastMCP server exposing garden/commute/utility tools. Entry point: `my_mcp/main.py`.
4. **email-sink** — IMAP email poller that watches for transit alert emails and POSTs them to `/process_alert`. Entry point: `email_sink/main.py`.

### Agent System (`app/agents/`)

Uses the `openai-agents` SDK (`from agents import Agent, Runner, function_tool`).

- **Orchestrator** (`orchestrator_agent.py`) — Triage agent that routes to specialized agents via `handoffs=[...]`. Created per-request with `create_orchestrator_agent(model)`.
- **Gardener** (`gardener_agent.py`) — Garden management. Calls MCP tools (`get_plants`, `add_plant`, `get_produce_counts`, `add_produce`) via `app/core/mcp_client.py`.
- **Commute** (`commute_agent.py`) — Seattle commute info. Uses `get_monorail_hours` tool and processes transit alert emails.
- **Scheduler** (`scheduler_agent.py`) — Converts natural language to scheduled tasks (cron/interval/date). Writes to `storage/scheduled_tasks.json` and reloads APScheduler. Management tools in `app/agents/scheduler/manage_tools.py`.

### Key API Endpoints (`app/core/main_router.py`)

- `POST /agent_response` — Main conversational endpoint. Runs Orchestrator agent, sends response to user via Telegram.
- `POST /process_alert` — Receives alerts from email sink, processes through agents, stores results.
- `POST /tasks`, `GET /tasks`, `DELETE /tasks/{id}` — Scheduled task CRUD.
- `POST /send_telegram_message` — Send Telegram messages (used by scheduled tasks).
- `POST /clear_conversation` — Clear conversation history.

All mutating endpoints require `X-Token` header authentication (see `app/core/auth.py`).

### Core Services (`app/core/`)

- **settings.py** — Pydantic `BaseSettings` singleton (`config`). All config from `.env` file. Use `Config.create_test_config(**kwargs)` in tests to avoid loading `.env`.
- **scheduler.py** — APScheduler service that reads `storage/scheduled_tasks.json`. Supports cron, interval, and one-time date schedules.
- **conversation_manager.py** — Manages conversation history for agent context.
- **agent_response_handler.py** — Parses `<json>...</json>` tags in agent responses for notification decisions (notify_user, message_content, rationale).
- **mcp_client.py** — HTTP client for calling MCP server tools.
- **telegram_client.py** — Sends messages to Telegram users.
- **task_store.py** — Read/write/delete scheduled tasks from JSON config file.

### MCP Server (`my_mcp/`)

Built with `fastmcp`. Tools organized by domain: `garden/tools.py`, `commute/tools.py`, `utils/tools.py`. Garden data stored in `storage/garden_db.json`.

### Persistent Storage (`storage/`)

JSON file-based storage: `garden_db.json`, `scheduled_tasks.json`, `task_results.json`, `commute_alerts.json`, `conversation_history.json`.

## Configuration Pattern

Settings are managed via `app/core/settings.py` using Pydantic `BaseSettings`. Add new settings by:
1. Adding a `Field` to the `Config` class in `settings.py`
2. Adding the env var to `.env.example`
3. Accessing via `from app.core.settings import config`

## Testing Conventions

- Tests in `tests/unit/`, `tests/integration/`, `tests/e2e/` mirroring source structure
- Pytest markers: `unit`, `integration`, `e2e`, `slow`, `app`, `telegram`, `mcp`
- Use `Config.create_test_config()` to create isolated test configs
- Use `@pytest.mark.asyncio` for async tests
- Use `@pytest.mark.parametrize` for multiple input/output scenarios

## Tech Stack

- Python 3.13+, `uv` for package management
- OpenAI Agents SDK (`openai-agents`) — always prefer this over direct OpenAI API calls
- FastAPI + Uvicorn
- FastMCP for MCP server
- APScheduler for task scheduling
- Loguru for logging
- Ruff for linting/formatting
- python-telegram-bot for Telegram integration
