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

# Pull the private agents repo too (separate repo cloned into my_agent_private).
# It gets baked into the image by `COPY .` in the Dockerfile.
PRIVATE_DIR="$REPO_DIR/my_agent_private"
if [ -d "$PRIVATE_DIR/.git" ]; then
  echo "Pulling private agents repo"
  if ! git -C "$PRIVATE_DIR" pull origin main; then
    echo "Failed to pull private agents repo"
    exit 1
  fi
fi

echo "Building and restarting Docker containers"
if ! docker compose -f docker-compose.yml down; then
  echo "Failed to stop Docker containers"
  exit 1
fi

# Pass build info through to the containers so /version reports the deployed commit
GIT_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
GIT_COMMIT_MESSAGE="$(git -C "$REPO_DIR" log -1 --pretty=%s)"
export GIT_COMMIT GIT_COMMIT_MESSAGE

if ! docker compose -f docker-compose.yml up -d --build; then
  echo "Failed to build and start Docker containers"
  exit 1
fi

echo "Deployment completed successfully"
