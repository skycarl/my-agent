#!/bin/bash

# Auto-deploy script: checks if origin/main has new commits and deploys if so.
# Intended to be run via cron every 5 minutes.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

PRIVATE_DIR="$REPO_DIR/my_agent_private"
changed=0

# Deploy only when origin/main has commits we don't have yet (a pull would
# actually change something). Checking `HEAD != origin/main` would also fire
# when local is *ahead* of remote (e.g. a stray local commit), causing an
# endless redeploy loop.
git fetch origin main
if ! git merge-base --is-ancestor origin/main HEAD; then
    changed=1
fi

# Also watch the private agents repo (a separate repo cloned in here), so
# pushing to it deploys automatically too — no manual step.
if [ -d "$PRIVATE_DIR/.git" ]; then
    git -C "$PRIVATE_DIR" fetch origin main
    if ! git -C "$PRIVATE_DIR" merge-base --is-ancestor origin/main HEAD; then
        changed=1
    fi
fi

if [ "$changed" -eq 0 ]; then
    exit 0
fi

echo "$(date): New commits detected, deploying..."
./deploy.sh
