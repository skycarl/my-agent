.PHONY: test lint run run-bot pre-commit install help docker-up docker-down

# Default target
help:
	@echo "Available targets:"
	@echo "  test       - Run tests with pytest"
	@echo "  lint       - Run ruff check for linting"
	@echo "  run        - Start the FastAPI server with reload"
	@echo "  run-bot    - Start the Telegram bot"
	@echo "  pre-commit - Run pre-commit hooks on all files"
	@echo "  install    - Install dependencies with uv"
	@echo "  docker-up  - Start services with docker-compose"
	@echo "  docker-down - Stop services with docker-compose"

test:
	uv run pytest

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

run:
	uv run python -m uvicorn app.main:app --reload

run-bot:
	uv run python -m app.telegram.main

run-mcp:
	uv run python -m my_mcp.main

pre-commit:
	uv run pre-commit run --all-files

install:
	uv sync

docker-up:
	docker compose up -d

docker-down:
	docker compose down
