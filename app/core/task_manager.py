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
                if task.type in ("api_call_only", "api_call_with_telegram"):
                    return await self._execute_api_call(task)
                elif task.type == "custom_function":
                    return await self._execute_custom_function(task)
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

            if task.type == "api_call_with_telegram":
                # If primary action succeeded, optionally send telegram
                if success and task.telegram:
                    telegram_success = await self._send_telegram_message(
                        task, response_data
                    )
                    result.success = success and telegram_success
                    if telegram_success:
                        result.result_data["telegram_sent"] = True
                    else:
                        result.result_data["telegram_sent"] = False
                        result.result_data["telegram_error"] = (
                            "Failed to send Telegram message"
                        )
                else:
                    result.success = success
            else:
                result.success = success

            result.completed_at = now_local()

            if result.success:
                logger.info(f"Task '{task.id}' completed successfully")
            else:
                logger.warning(f"Task '{task.id}' completed with errors")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task '{task.id}' failed with error: {error_msg}")

            result.success = False
            result.error_message = error_msg
            result.completed_at = now_local()

            # Send error to Telegram if configured
            if (
                task.type == "api_call_with_telegram"
                and task.telegram
                and task.telegram.send_on_error
            ):
                try:
                    await self._send_error_to_telegram(task, error_msg)
                except Exception as telegram_error:
                    logger.error(f"Failed to send error to Telegram: {telegram_error}")

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

    async def _execute_custom_function(
        self, task: TaskConfig
    ) -> Tuple[bool, Dict[str, Any]]:
        """Execute a custom function task."""
        if not task.custom_function:
            return False, {"error": "No custom function configuration provided"}

        function_name = task.custom_function.function_name
        parameters = task.custom_function.parameters

        logger.debug(f"Executing custom function: {function_name}")

        # Registry of available custom functions
        custom_functions = {
            "s3_backup": self._s3_backup_function,
            # Add more custom functions here as needed
        }

        if function_name not in custom_functions:
            return False, {"error": f"Unknown custom function: {function_name}"}

        try:
            result = await custom_functions[function_name](parameters)
            return True, result
        except Exception as e:
            error_msg = f"Custom function {function_name} failed: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}

    async def _s3_backup_function(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Example custom function for S3 backup (placeholder)."""
        # This is a placeholder - actual S3 backup implementation would go here
        logger.info("S3 backup function called (placeholder implementation)")
        return {
            "message": "S3 backup completed successfully (placeholder)",
            "files_backed_up": 0,
            "timestamp": now_local().isoformat(),
        }

    async def _send_telegram_message(
        self, task: TaskConfig, response_data: Dict[str, Any]
    ) -> bool:
        """Send task result to Telegram."""
        if not task.telegram:
            return False

        try:
            # If the API endpoint already sent the Telegram message (e.g. /agent_response),
            # avoid sending a duplicate here.
            if isinstance(response_data.get("response"), dict):
                inner_response = response_data["response"]
                if inner_response.get("response_sent") is True:
                    logger.info(
                        "API endpoint already delivered the message via Telegram; skipping duplicate send"
                    )
                    return True

            # Extract the message from the API response
            message_text = self._format_telegram_message(task, response_data)

            # If formatting produced an empty message (e.g. endpoint already sent it), skip
            if not message_text or not message_text.strip():
                logger.debug(
                    "No Telegram message content after formatting; skipping send"
                )
                return True

            # Add prefix if configured
            if task.telegram.message_prefix:
                message_text = f"{task.telegram.message_prefix}\n\n{message_text}"

            # Determine target user
            target_user_id = task.telegram.user_id or config.authorized_user_id

            # Create message request
            telegram_request = TelegramMessageRequest(
                user_id=target_user_id, message=message_text
            )

            # Send via internal API
            headers = {"Content-Type": "application/json", "X-Token": config.x_token}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{config.app_url}/send_telegram_message",
                    json=telegram_request.model_dump(),
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.debug("Telegram message sent successfully")
                    return True
                else:
                    logger.warning(
                        f"Failed to send Telegram message: {response.status_code}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def _send_error_to_telegram(
        self, task: TaskConfig, error_message: str
    ) -> None:
        """Send error message to Telegram."""
        if not task.telegram:
            return

        try:
            # Format error message
            message_text = f"❌ Task '{task.name}' failed:\n\n{error_message}"

            # Add prefix if configured
            if task.telegram.message_prefix:
                message_text = f"{task.telegram.message_prefix}\n\n{message_text}"

            # Determine target user
            target_user_id = task.telegram.user_id or config.authorized_user_id

            # Create message request
            telegram_request = TelegramMessageRequest(
                user_id=target_user_id, message=message_text
            )

            # Send via internal API
            headers = {"Content-Type": "application/json", "X-Token": config.x_token}

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{config.app_url}/send_telegram_message",
                    json=telegram_request.model_dump(),
                    headers=headers,
                    timeout=30.0,
                )

        except Exception as e:
            logger.error(f"Error sending error message to Telegram: {e}")

    def _format_telegram_message(
        self, task: TaskConfig, response_data: Dict[str, Any]
    ) -> str:
        """Format the response data for Telegram message."""
        try:
            # Try to extract the main response content
            if "response" in response_data and isinstance(
                response_data["response"], dict
            ):
                inner = response_data["response"]
                # If the endpoint already sent the message, return empty string so caller can skip
                if inner.get("response_sent") is True:
                    return ""
                # If the endpoint returned the actual text under 'response', use it
                if "response" in inner and inner["response"]:
                    return str(inner["response"])
                # Otherwise, if a human-readable message exists, use it
                if "message" in inner and inner["message"]:
                    return str(inner["message"])
                # Fallback to JSON dump of the inner payload
                return json.dumps(inner, indent=2)
            elif "response" in response_data:
                return str(response_data["response"])
            elif "message" in response_data:
                return str(response_data["message"])
            else:
                # Fallback to JSON representation
                return json.dumps(response_data, indent=2)

        except Exception as e:
            logger.warning(f"Error formatting Telegram message: {e}")
            return f"Task '{task.name}' completed, but response formatting failed."

        # This should never be reached, but mypy needs it
        return "Task completed, but response formatting failed."

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
