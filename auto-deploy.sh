#!/bin/bash

# Auto-deploy script: checks if origin/main has new commits and deploys if so.
# Intended to be run via cron every 5 minutes.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

PRIVATE_DIR="$REPO_DIR/my_agent_private"
changed=0

git fetch origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    changed=1
fi

# Also watch the private agents repo (a separate repo cloned in here), so
# pushing to it deploys automatically too — no manual step.
if [ -d "$PRIVATE_DIR/.git" ]; then
    git -C "$PRIVATE_DIR" fetch origin main
    if [ "$(git -C "$PRIVATE_DIR" rev-parse HEAD)" != "$(git -C "$PRIVATE_DIR" rev-parse origin/main)" ]; then
        changed=1
    fi
fi

if [ "$changed" -eq 0 ]; then
    exit 0
fi

echo "$(date): New commits detected, deploying..."
./deploy.sh
