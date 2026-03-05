#!/bin/bash

# Auto-deploy script: checks if origin/main has new commits and deploys if so.
# Intended to be run via cron every 5 minutes.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

echo "$(date): New commits detected, deploying..."
./deploy.sh
