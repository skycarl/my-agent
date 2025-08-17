"""
Task configuration models for the scheduler service.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class TaskSchedule(BaseModel):
    """Task schedule configuration."""

    type: Literal["cron", "interval", "date"] = Field(
        description=(
            "Schedule type: 'cron' for cron expressions, 'interval' for simple intervals, "
            "'date' for a one-time run at a specific datetime"
        )
    )
    expression: Optional[str] = Field(
        default=None, description="Cron expression (e.g., '0 7 * * *' for daily at 7am)"
    )
    interval_seconds: Optional[int] = Field(
        default=None, description="Interval in seconds for interval-based schedules"
    )
    run_at: Optional[datetime] = Field(
        default=None,
        description=(
            "Datetime at which a one-time task should run. If timezone-naive, it will be interpreted "
            "in the configured scheduler timezone. Only valid when type='date'"
        ),
    )

    def model_post_init(self, __context) -> None:
        """Validate that the correct fields are provided based on schedule type."""
        if self.type == "cron":
            if not self.expression:
                raise ValueError("Cron expression is required for cron schedule type")
            if self.interval_seconds is not None:
                raise ValueError(
                    "Cannot specify interval_seconds for cron schedule type"
                )
            if self.run_at is not None:
                raise ValueError("Cannot specify run_at for cron schedule type")
        elif self.type == "interval":
            if not self.interval_seconds:
                raise ValueError(
                    "Interval seconds is required for interval schedule type"
                )
            if self.expression is not None:
                raise ValueError(
                    "Cannot specify cron expression for interval schedule type"
                )
            if self.run_at is not None:
                raise ValueError("Cannot specify run_at for interval schedule type")
        elif self.type == "date":
            if self.run_at is None:
                raise ValueError("run_at is required for date schedule type")
            if self.expression is not None:
                raise ValueError(
                    "Cannot specify cron expression for date schedule type"
                )
            if self.interval_seconds is not None:
                raise ValueError(
                    "Cannot specify interval_seconds for date schedule type"
                )


class APICallConfig(BaseModel):
    """Configuration for API call tasks."""

    endpoint: str = Field(description="API endpoint to call (e.g., '/agent_response')")
    method: str = Field(default="POST", description="HTTP method to use")
    payload: Dict[str, Any] = Field(description="Request payload/body")
    headers: Optional[Dict[str, str]] = Field(
        default=None, description="Additional headers to include"
    )
    timeout: int = Field(default=120, description="Request timeout in seconds")


# Removed TelegramConfig and CustomFunctionConfig as sending is owned by the
# /agent_response endpoint and we only support API call tasks.


class TaskConfig(BaseModel):
    """Main task configuration model."""

    id: str = Field(description="Unique task identifier")
    name: str = Field(description="Human-readable task name")
    type: Literal["api_call"] = Field(description="Type of task to execute")
    enabled: bool = Field(default=True, description="Whether the task is enabled")
    schedule: TaskSchedule = Field(description="Task schedule configuration")

    # Task-specific configurations
    api_call: Optional[APICallConfig] = Field(
        default=None, description="API call configuration (required for api_call tasks)"
    )

    # Task metadata
    description: Optional[str] = Field(default=None, description="Task description")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")
    retry_delay: int = Field(default=60, description="Delay between retries in seconds")

    def model_post_init(self, __context) -> None:
        """Validate that required configurations are provided based on task type."""
        if self.type == "api_call" and not self.api_call:
            raise ValueError(
                f"api_call configuration is required for task type '{self.type}'"
            )


class TasksConfiguration(BaseModel):
    """Root configuration containing all tasks."""

    tasks: List[TaskConfig] = Field(
        default_factory=list, description="List of task configurations"
    )
    version: str = Field(default="1.0", description="Configuration file version")
    last_modified: Optional[datetime] = Field(
        default=None, description="Last modification timestamp"
    )


class TaskExecutionResult(BaseModel):
    """Result of a task execution."""

    task_id: str = Field(description="ID of the executed task")
    execution_id: str = Field(description="Unique execution identifier")
    started_at: datetime = Field(description="Task start timestamp")
    completed_at: Optional[datetime] = Field(
        default=None, description="Task completion timestamp"
    )
    success: bool = Field(description="Whether the task completed successfully")
    error_message: Optional[str] = Field(
        default=None, description="Error message if task failed"
    )
    result_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Task result data"
    )
    retry_count: int = Field(default=0, description="Number of retries performed")
    next_retry_at: Optional[datetime] = Field(
        default=None, description="Next retry timestamp if applicable"
    )


class TaskResultsStorage(BaseModel):
    """Storage model for task execution results."""

    results: List[TaskExecutionResult] = Field(
        default_factory=list, description="List of task execution results"
    )
    max_results: int = Field(
        default=1000, description="Maximum number of results to keep"
    )

    def add_result(self, result: TaskExecutionResult) -> None:
        """Add a new result and maintain the maximum results limit."""
        self.results.append(result)

        # Keep only the most recent results
        if len(self.results) > self.max_results:
            self.results = self.results[-self.max_results :]

    def get_results_for_task(
        self, task_id: str, limit: int = 10
    ) -> List[TaskExecutionResult]:
        """Get recent results for a specific task."""
        task_results = [r for r in self.results if r.task_id == task_id]
        return sorted(task_results, key=lambda x: x.started_at, reverse=True)[:limit]


class TelegramMessageRequest(BaseModel):
    """Request model for sending Telegram messages."""

    user_id: Optional[int] = Field(
        default=None, description="Telegram user ID (null = use authorized user)"
    )
    message: str = Field(description="Message text to send")
    parse_mode: Optional[str] = Field(
        default=None, description="Telegram parse mode (e.g., 'Markdown', 'HTML')"
    )


class TelegramMessageResponse(BaseModel):
    """Response model for Telegram message sending."""

    success: bool = Field(description="Whether the message was sent successfully")
    message: str = Field(description="Status message")
    telegram_message_id: Optional[int] = Field(
        default=None, description="Telegram message ID if successful"
    )


class AgentProcessingMetadata(BaseModel):
    """Metadata about agent processing of an alert."""

    success: bool = Field(description="Whether agent processing completed successfully")
    primary_agent: Optional[str] = Field(
        default=None, description="Name of the primary agent that processed the alert"
    )
    actions_taken: List[str] = Field(
        default_factory=list, description="List of actions/tools the agent used"
    )
    agent_response: Optional[str] = Field(
        default=None, description="Final response from the agent"
    )
    processing_time_ms: Optional[int] = Field(
        default=None, description="Time taken for agent processing in milliseconds"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if processing failed"
    )


class AlertRequest(BaseModel):
    """Request model for posting alerts to internal endpoints (formerly CommuteAlertRequest)."""

    uid: str
    subject: str
    body: str
    sender: str
    date: datetime
    alert_type: str = Field(default="email", description="Type of alert")


class AlertResponse(BaseModel):
    """Response model for alert processing (formerly CommuteAlertResponse)."""

    success: bool = Field(description="Whether the alert was processed successfully")
    message: str = Field(description="Status message")
    alert_id: str = Field(description="Unique identifier for the stored alert")
    agent_processing: Optional[AgentProcessingMetadata] = Field(
        default=None, description="Metadata about agent processing"
    )
