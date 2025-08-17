"""
Task manager for executing scheduled tasks and handling results.
"""

import json
import asyncio
from datetime import timedelta
import uuid
import httpx
from pathlib import Path
from typing import Dict, Any, Tuple
from loguru import logger

from app.core.settings import config
from app.core.timezone_utils import now_local
from app.models.tasks import (
    TaskConfig,
    TaskExecutionResult,
    TaskResultsStorage,
    TelegramMessageRequest,
)


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
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Error loading task results file: {e}")
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
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(
                    self.results_storage.model_dump(),
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str,  # Handle datetime serialization
                )
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
                if task.type == "api_call":
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
                # Notify on non-exception failures as well (e.g., non-2xx HTTP)
                try:
                    error_summary = result.error_message or (
                        f"HTTP {response_data.get('status_code')} - "
                        f"{response_data.get('error') or response_data.get('response')}"
                        if isinstance(response_data, dict)
                        else str(response_data)
                    )
                    await self._notify_error_via_endpoint(task, str(error_summary))
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

    async def _execute_api_call(self, task: TaskConfig) -> Tuple[bool, Dict[str, Any]]:
        """Execute an API call task."""
        if not task.api_call:
            return False, {"error": "No API call configuration provided"}

        try:
            # Prepare headers
            headers = {"Content-Type": "application/json", "X-Token": config.x_token}

            # Add any additional headers
            if task.api_call.headers:
                headers.update(task.api_call.headers)

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
            target_user_id = config.authorized_user_id
            telegram_request = TelegramMessageRequest(
                user_id=target_user_id, message=message_text
            )
            headers = {"Content-Type": "application/json", "X-Token": config.x_token}

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{config.app_url}/send_telegram_message",
                    json=telegram_request.model_dump(),
                    headers=headers,
                    timeout=30.0,
                )
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")

    def get_task_results(self, task_id: str, limit: int = 10) -> list:
        """Get recent results for a specific task."""
        return self.results_storage.get_results_for_task(task_id, limit)

    def get_all_recent_results(self, limit: int = 50) -> list:
        """Get recent results for all tasks."""
        return sorted(
            self.results_storage.results, key=lambda x: x.started_at, reverse=True
        )[:limit]


# Create a global task manager instance
task_manager = TaskManager()
