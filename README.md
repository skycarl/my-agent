<h1 align="center"> 
My Agent
</h1>

<h2 align="center">
</h2>

# Overview

The goal of this project is to:

1. Create an agent that can help me with my daily life
2. Play with the OpenAI Agents SDK
3. Have fun building it! 

## Usage

There are 4 main agents:
- The `Orchestrator` agent
   - This agent is the main entry point and decides which specialized agent should handle each request through agent handoffs.
- The `Gardener` agent
   - This agent is responsible for managing my garden.
- The `Commute` agent
   - This agent is responsible for managing my commute.
- The `Scheduler` agent
   - This agent is responsible for scheduling tasks (e.g., as recurring or one-time prompts)

### Gardener

The `Gardener` agent manages your garden data: it helps you track plants, record harvests, and view simple statistics about my yields. It is backed by MCP tools that read and write to the garden store, so answers and actions are grounded in structured data rather than guesswork. It uses the tools `get_plants`, `add_plant`, `get_produce_counts`, and `add_produce` to add/fetch records to/from persistent storage.

### Commute

The `Commute` agent focuses on commute-related information for the Seattle area. It uses a `get_monorail_hours` tool to fetch the current operating hours of the Seattle monorail from its website. The Commute agent also processes transportation alerts via email from Sound Transit. It determines whether an alert is relevant (e.g., delays, service disruptions, weather impacts) and crafts a short notification only when I should be notified, ignoring non-commute items like elevator or vending machine outages that don't impact my commute to reduce notification fatigue. 

### Scheduler

The `Scheduler` agent converts natural-language instructions into scheduled tasks. It exclusively schedules API calls to `/agent_response`, enabling reminders and recurring prompts to be triggered automatically without manual follow-up. It supports three schedule types—`cron`, `interval`, and one-time `date`—and can also list and delete tasks via `list_scheduled_tasks` and `delete_scheduled_task`.

# Setup

## Prerequisites

- Docker
- Docker Compose
- Python 3.13+
- `uv`

## Configuration
This project uses `pydantic-settings` for settings management.

Create **.env** file in root project folder; use the provided `env.example` file as a template. The application settings are managed by `app/core/settings.py` which uses Pydantic BaseSettings for configuration.

# Telegram Bot integration

This project uses a Telegram bot as the conversational interface.

## Setting Up the Telegram Bot

1. **Create a Telegram Bot:**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Use `/newbot` command to create a new bot
   - Follow the instructions and get the bot token
   - Add the token to `.env` file as `TELEGRAM_BOT_TOKEN`

2. **Configure OpenAI:**
   - Get an OpenAI API key from [OpenAI Platform](https://platform.openai.com/api-keys)
   - Add it to `.env` file as `OPENAI_API_KEY`

## Running services

```bash
# Start both API and Telegram bot services
make docker-up

# Stop services
make docker-down
```

## MCP Integration

The application includes a Model Context Protocol (MCP) integration that automatically makes garden management tools available to the AI assistant. The MCP server exposes tools for:

- **get_plants**: List all plants in the garden with their yields
- **add_plant**: Add a new plant to the garden
- **get_produce_counts**: Get harvest statistics for a specific plant
- **add_produce**: Record a new harvest for a plant



# Ideas

- [x] Sink for alert message subscriptions
- [x] Task scheduler for running scheduled tasks
- [ ] Calendar integration to integrate with text sinks
- [ ] Back up local storage to S3 
- [ ] Integrate with Obsidian notes 
   - [ ] Send a recipe link --> grab the recipe --> save it to my Obsidian notes recipe section 
- [ ] Fetch current status of alerts from Sound Transit
- [ ] Persist message history (to include alert history) on disk rather than in memory for consistent conversation history
   - [ ] Handle duplicated alerts by checking conversation history, and only send a new alert if there is new information 
- [ ] Memory for keeping track of when the user is and isn't commuting, so the agents can ignore commute alerts when they are not commuting
- [ ] Ability to update the scheduled tasks file via conversation
- [ ] BAML for prompts and output parsing
- [x] Fix agent default models
- [ ] Analyze firewall alerts from pfSense
- [ ] Review async logic for the agent_response endpoint; how is this working for multiple concurrent requests?