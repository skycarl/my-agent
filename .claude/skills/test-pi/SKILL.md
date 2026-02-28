---
name: test-pi
description: Test the my-agent deployment on the Raspberry Pi over the local network. Use when testing endpoints, checking service health, or debugging the Pi deployment.
allowed-tools: Bash(curl *), Bash(ping *), Bash(ssh *)
argument-hint: [endpoint-or-action]
---

# Test Raspberry Pi Deployment

Test the my-agent app running on the Raspberry Pi at `192.168.1.247`.

## Connection Details

- **Pi host**: `192.168.1.247` (alias: `pi5` = `ssh sky@192.168.1.247`)
- **App port**: `8001` (FastAPI)
- **MCP port**: `8002` (FastMCP)
- **Base URL**: `http://192.168.1.247:8001`
- **Auth header**: `X-Token: 123`

## Available Endpoints

### No auth required
- `GET /healthcheck` — Returns `{"status": "healthy"}`
- `GET /models` — Returns available models and default model

### Auth required (include `-H "X-Token: 123"`)
- `GET /tasks` — List scheduled tasks. Query params: `only_enabled=true`, `name_filter=...`
- `POST /tasks` — Create a scheduled task (JSON body)
- `DELETE /tasks/{task_id}` — Delete a scheduled task
- `POST /agent_response` — Send a message through the agent system (JSON body: `{"input": "..."}`)
- `POST /process_alert` — Process an alert through agents
- `POST /clear_conversation` — Clear conversation history
- `POST /send_telegram_message` — Send a Telegram message (JSON body: `{"message": "..."}`)

## How to Test

Use curl from this machine to hit the Pi over the local network:

```bash
# Health check
curl -s http://192.168.1.247:8001/healthcheck | python3 -m json.tool

# List models
curl -s http://192.168.1.247:8001/models | python3 -m json.tool

# List tasks
curl -s -H "X-Token: 123" http://192.168.1.247:8001/tasks | python3 -m json.tool

# Check Docker containers on Pi
ssh sky@192.168.1.247 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'

# Check Docker logs
ssh sky@192.168.1.247 'docker compose -f /home/sky/apps/my-agent/docker-compose.yml logs --tail=20'

# Check specific container logs
ssh sky@192.168.1.247 'docker compose -f /home/sky/apps/my-agent/docker-compose.yml logs --tail=20 app'
```

## Test Sequence

When running a full test (`/test-pi` with no arguments), run this sequence:

1. **Connectivity**: Ping the Pi
2. **Docker**: Check all 4 containers are running (app, telegram_bot, mcp_server, email_sink)
3. **Health**: Hit `/healthcheck`
4. **Models**: Hit `/models` and verify default model
5. **Tasks**: Hit `GET /tasks` to list scheduled tasks
6. **MCP**: Check MCP server is responding on port 8002

When `$ARGUMENTS` specifies a particular endpoint or action, test just that.

Report results clearly with pass/fail for each check.
