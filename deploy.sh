#!/bin/bash

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$REPO_DIR/deploy-logs"
mkdir -p "$LOG_DIR"

log_file="$LOG_DIR/deploy-$(date '+%Y%m%d-%H%M%S').log"
exec > >(tee -i "$log_file")
exec 2>&1

echo "Pulling from git"
if ! git pull origin main; then
  echo "Failed to pull from git"
  exit 1
fi

echo "Building and restarting Docker containers"
if ! docker compose -f docker-compose.yml down; then
  echo "Failed to stop Docker containers"
  exit 1
fi

if ! docker compose -f docker-compose.yml up -d --build; then
  echo "Failed to build and start Docker containers"
  exit 1
fi

echo "Deployment completed successfully"
