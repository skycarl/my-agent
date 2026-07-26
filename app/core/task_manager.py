"""
Task manager for executing scheduled tasks and handling results.
"""

import json
import asyncio
import os
from datetime import timedelta
import uuid
import httpx
from pathlib import Path
from typing import Dict, Any, Tuple
from loguru import logger

from app.core.settings import config
from app.core.timezone_utils import now_local
from app.core.telegram_client import telegram_client
from app.models.tasks import (
    TaskConfig,
    TaskExecutionResult,
    TaskResultsStorage,
    TelegramMessageRequest,
)

ALLOWED_TASK_ENDPOINTS = frozenset({"/agent_response"})


class TaskManager:
    """Manages task execution and result storage."""

    def __init__(self):
        """Initialize the task manager."""
        self.results_storage = self._load_results_storage()
        logger.debug("Task manager initialized")

    def _load_results_storage(self) -> TaskResultsStorage:
        """Load task results from storage file."""
        results_file = Path(config.task_results_path)

        if results_file.exists():
            try:
                with open(results_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return TaskResultsStorage(**data)
            except Exception as e:
                logger.error(f"Error loading task results file: {e}")
                # Create new storage if file is corrupted
                return TaskResultsStorage()
        else:
            # Create new storage if file doesn't exist
            return TaskResultsStorage()

    def _save_results_storage(self) -> None:
        """Save task results to storage file."""
        results_file = Path(config.task_results_path)
        results_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Write to a temp file and rename: a crash mid-write would
            # otherwise leave truncated JSON, which _load_results_storage
            # discards wholesale on the next start.
            tmp_file = results_file.with_suffix(".json.tmp")
            tmp_file.write_text(
                json.dumps(
                    self.results_storage.model_dump(),
                    indent=2,
                    ensure_ascii=False,
                    default=str,  # Handle datetime serialization
                ),
                encoding="utf-8",
            )
            os.replace(tmp_file, results_file)
        except Exception as e:
            logger.error(f"Failed to save task results: {e}")

    async def execute_task(self, task: TaskConfig) -> TaskExecutionResult:
        """
        Execute a single task and return the result.

        Args:
            task: Task configuration to execute

        Returns:
            Task execution result
        """
        execution_id = str(uuid.uuid4())
        started_at = now_local()

        logger.info(f"Executing task '{task.id}' (execution_id: {execution_id})")

        # Create initial result
        result = TaskExecutionResult(
            task_id=task.id,
            execution_id=execution_id,
            started_at=started_at,
            success=False,
        )

        try:
            # Simple retry mechanism around the primary action
            max_retries = max(0, task.max_retries)
            retry_delay = max(0, task.retry_delay)
            attempt = 0
            success = False
            response_data: Dict[str, Any] = {}

            async def run_primary_action() -> tuple[bool, Dict[str, Any]]:
                if task.mode == "notify":
                    return await self._execute_notification(task)
                elif task.type == "api_call":
                    return await self._execute_api_call(task)
                else:
                    raise ValueError(f"Unknown task type: {task.type}")

            while True:
                success, response_data = await run_primary_action()
                if success or attempt >= max_retries:
                    break
                attempt += 1
                result.retry_count = attempt
                result.next_retry_at = now_local() + timedelta(seconds=retry_delay)
                logger.warning(
                    f"Task '{task.id}' attempt {attempt} failed. Retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)

            # Prepare result data
            result.result_data = response_data

            # With endpoint-owned sending, task manager just records success of API call
            result.success = success

            result.completed_at = now_local()

            if result.success:
                logger.info(f"Task '{task.id}' completed successfully")
            else:
                logger.warning(f"Task '{task.id}' completed with errors")
                # Record why (status + response snippet) so stored results and
                # run_scheduled_task_now don't report "unknown error"
                if not result.error_message:
                    if isinstance(response_data, dict):
                        status = response_data.get("status_code")
                        detail = response_data.get("response") or response_data.get(
                            "error"
                        )
                        result.error_message = (
                            f"HTTP {status} - {detail}" if status else str(detail)
                        )
                    else:
                        result.error_message = str(response_data)
                # Notify on non-exception failures as well (e.g., non-2xx HTTP)
                try:
                    await self._notify_error_via_endpoint(task, result.error_message)
                except Exception as telegram_error:
                    logger.error(
                        f"Failed to send error notification (non-exception failure): {telegram_error}"
                    )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task '{task.id}' failed with error: {error_msg}")

            result.success = False
            result.error_message = error_msg
            result.completed_at = now_local()

            # Send error to Telegram if configured
            # On error, send a simple notification via the internal endpoint
            try:
                await self._notify_error_via_endpoint(task, error_msg)
            except Exception as telegram_error:
                logger.error(f"Failed to send error notification: {telegram_error}")

        # Store the result
        self.results_storage.add_result(result)
        self._save_results_storage()

        return result

    async def _execute_notification(
        self, task: TaskConfig
    ) -> Tuple[bool, Dict[str, Any]]:
        """Execute a notify-mode task by sending a message directly via Telegram."""
        if not task.notification:
            return False, {"error": "No notification configuration provided"}

        try:
            target_user_id = (
                int(task.conversation_id)
                if task.conversation_id
                else config.owner_user_id
            )
            success, message_id = await telegram_client.send_message(
                user_id=target_user_id,
                message=task.notification.message,
                parse_mode=task.notification.parse_mode,
            )

            if success:
                logger.debug(
                    f"Notification sent for task '{task.id}', message_id={message_id}"
                )
                return True, {
                    "telegram_message_id": message_id,
                    "message": task.notification.message,
                }
            else:
                return False, {"error": "Telegram send_message returned failure"}

        except Exception as e:
            error_msg = f"Notification failed: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}

    async def _execute_api_call(self, task: TaskConfig) -> Tuple[bool, Dict[str, Any]]:
        """Execute an API call task."""
        if not task.api_call:
            return False, {"error": "No API call configuration provided"}

        # Validate endpoint against allowlist
        normalized_endpoint = "/" + task.api_call.endpoint.lstrip("/")
        if normalized_endpoint not in ALLOWED_TASK_ENDPOINTS:
            error_msg = f"Endpoint not allowed: {task.api_call.endpoint}. Allowed: {', '.join(sorted(ALLOWED_TASK_ENDPOINTS))}"
            logger.error(f"Task '{task.id}': {error_msg}")
            return False, {"error": error_msg}

        try:
            # Prepare headers
            headers = {}
            if task.api_call.headers:
                headers.update(task.api_call.headers)
            # Ensure auth and content-type cannot be overridden by task config
            headers["Content-Type"] = "application/json"
            headers["X-Token"] = config.x_token
            # Signal to endpoint that this is a scheduled invocation
            headers["X-Scheduled-Task"] = "true"

            # Build the full URL
            base_url = config.app_url.rstrip("/")
            endpoint = task.api_call.endpoint.lstrip("/")
            url = f"{base_url}/{endpoint}"

            logger.debug(f"Making {task.api_call.method} request to {url}")

            # Make the API call
            async with httpx.AsyncClient() as client:
                if task.api_call.method.upper() == "GET":
                    response = await client.get(
                        url, headers=headers, timeout=task.api_call.timeout
                    )
                elif task.api_call.method.upper() == "POST":
                    response = await client.post(
                        url,
                        json=task.api_call.payload,
                        headers=headers,
                        timeout=task.api_call.timeout,
                    )
                elif task.api_call.method.upper() == "PUT":
                    response = await client.put(
                        url,
                        json=task.api_call.payload,
                        headers=headers,
                        timeout=task.api_call.timeout,
                    )
                else:
                    return False, {
                        "error": f"Unsupported HTTP method: {task.api_call.method}"
                    }

                # Parse response
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = {"text": response.text}

                if response.status_code >= 200 and response.status_code < 300:
                    logger.debug(f"API call successful: {response.status_code}")
                    return True, {
                        "status_code": response.status_code,
                        "response": response_data,
                    }
                else:
                    logger.warning(f"API call failed: {response.status_code}")
                    return False, {
                        "status_code": response.status_code,
                        "response": response_data,
                        "error": f"HTTP {response.status_code}",
                    }

        except httpx.TimeoutException:
            error_msg = f"API call timed out after {task.api_call.timeout} seconds"
            logger.warning(error_msg)
            return False, {"error": error_msg}

        except Exception as e:
            error_msg = f"API call failed: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}

    # Removed custom function support; TaskManager now only supports 'api_call' tasks.

    async def _notify_error_via_endpoint(
        self, task: TaskConfig, error_message: str
    ) -> None:
        """Notify the user of a task error via the internal send_telegram_message endpoint."""
        try:
            message_text = f"❌ Task '{task.name}' failed:\n\n{error_message}"
            target_user_id = (
                int(task.conversation_id)
                if task.conversation_id
                else config.owner_user_id
            )
            telegram_request = TelegramMessageRequest(
                user_id=target_user_id, message=message_text
            )
            headers = {"Content-Type": "application/json", "X-Token": config.x_token}

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{config.app_url.rstrip('/')}/send_telegram_message",
                    json=telegram_request.model_dump(),
                    headers=headers,
                    timeout=30.0,
                )
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")


# Create a global task manager instance
task_manager = TaskManager()
