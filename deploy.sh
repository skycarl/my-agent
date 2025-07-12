#!/bin/bash

set -e

log_file="deploy.log"
exec > >(tee -i $log_file)
exec 2>&1

echo "Pulling from git"
if ! git pull git@github.com:skycarl/my-agent.git; then
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
