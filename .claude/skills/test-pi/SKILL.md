---
name: test-pi
description: Test the my-agent deployment on the Raspberry Pi (over SSH; the app port is loopback-only). Use when testing endpoints, checking service health, or debugging the Pi deployment.
allowed-tools: Bash(curl *), Bash(ping *), Bash(ssh *)
argument-hint: [endpoint-or-action]
---

# Test Raspberry Pi Deployment

Test the my-agent app running on the Raspberry Pi at `192.168.1.247`.

## Connection Details

- **Pi host**: `192.168.1.247` (alias: `pi5` = `ssh sky@192.168.1.247`)
- **App port**: `8001` (FastAPI)
- **Base URL**: `http://localhost:8001` **on the Pi**. The port is published on
  `127.0.0.1` only (see `docker-compose.yml`), so `http://192.168.1.247:8001` from
  this machine is refused. Run curl on the Pi over SSH, or open a tunnel.
- **Auth header**: `X-Token: <X_TOKEN from the Pi's ~/apps/my-agent/.env>`. Build it
  on the Pi (see below). The laptop's `.env` token differs. Never hard-code it in this
  file, which is checked into a public repo.

## Available Endpoints

### No auth required
- `GET /healthcheck` — Returns `{"status": "healthy"}`
- `GET /models` — Returns available models and default model

### Auth required (`X-Token` header, see below)
- `GET /tasks` — List scheduled tasks. Query params: `only_enabled=true`, `name_filter=...`
- `POST /tasks` — Create a scheduled task (JSON body)
- `DELETE /tasks/{task_id}` — Delete a scheduled task
- `POST /agent_response` — Send a message through the agent system (JSON body: `{"input": "..."}`)
- `POST /process_alert` — Process an alert through agents
- `POST /clear_conversation` — Clear conversation history
- `POST /send_telegram_message` — Send a Telegram message (JSON body: `{"message": "..."}`)

## How to Test

Run curl on the Pi over SSH (the app port isn't reachable from the LAN):

```bash
# Health check
ssh sky@192.168.1.247 'curl -s http://localhost:8001/healthcheck' | python3 -m json.tool

# List models
ssh sky@192.168.1.247 'curl -s http://localhost:8001/models' | python3 -m json.tool

# List tasks. Build the auth header on the Pi from the Pi's own .env and feed it to
# curl on stdin (`-H @-`), so the token never leaves the Pi or appears on a command line.
# (The laptop's .env has a different X_TOKEN and won't authenticate against the Pi.)
ssh sky@192.168.1.247 'cd ~/apps/my-agent && sed -n "s/^X_TOKEN=/X-Token: /p" .env \
  | curl -s -H @- http://localhost:8001/tasks' | python3 -m json.tool

# Alternatively, for several calls or POST bodies, open a tunnel and curl localhost:
#   ssh -fN -L 8001:localhost:8001 sky@192.168.1.247
#   curl -s http://localhost:8001/healthcheck
#   (close it afterwards: pkill -f 'L 8001:localhost:8001')

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
2. **Docker**: Check all 3 containers are running (app, telegram_bot, email_sink)
3. **Health**: Hit `/healthcheck`
4. **Models**: Hit `/models` and verify default model
5. **Tasks**: Hit `GET /tasks` to list scheduled tasks

When `$ARGUMENTS` specifies a particular endpoint or action, test just that.

Report results clearly with pass/fail for each check.
