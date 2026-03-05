.PHONY: test lint run run-bot pre-commit install help docker-up docker-down setup-cron

# Default target
help:
	@echo "Available targets:"
	@echo "  test           - Run all tests with pytest"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-e2e       - Run end-to-end tests only"
	@echo "  test-app       - Run app service unit tests"
	@echo "  test-telegram  - Run telegram bot unit tests"
	@echo "  lint           - Run ruff check for linting"
	@echo "  run            - Start the FastAPI server with reload"
	@echo "  run-bot        - Start the Telegram bot"
	@echo "  pre-commit     - Run pre-commit hooks on all files"
	@echo "  install        - Install dependencies with uv"
	@echo "  docker-up      - Start services with docker-compose"
	@echo "  docker-down    - Stop services with docker-compose"

test:
	uv run pytest tests/

test-unit:
	uv run pytest tests/unit/

test-integration:
	uv run pytest tests/integration/

test-e2e:
	uv run pytest tests/e2e/

test-app:
	uv run pytest tests/unit/app/

test-telegram:
	uv run pytest tests/unit/telegram_bot/

lint:
	uv run ruff format && uv run ruff check

run:
	uv run python -m uvicorn app.main:app --reload

run-bot:
	uv run python -m app.telegram.main

pre-commit:
	uv run pre-commit run --all-files

install:
	uv sync

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

logs:
	docker compose -f docker-compose.yml logs -f

setup-cron:
	@echo "Run this on your Pi to add the cron job:"
	@echo '  (crontab -l 2>/dev/null; echo "*/5 * * * * $(CURDIR)/auto-deploy.sh >> $(CURDIR)/auto-deploy.log 2>&1") | crontab -'