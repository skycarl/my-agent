"""
Task scheduler service with APScheduler integration and hot reload functionality.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from app.core.settings import config
from app.core.task_manager import task_manager
from app.models.tasks import TaskConfig, TasksConfiguration
from app.core.timezone_utils import (
    now_local_isoformat,
    get_scheduler_timezone,
    ensure_timezone,
)


class SchedulerService:
    """Main scheduler service with APScheduler integration and hot reload."""

    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler = AsyncIOScheduler(timezone=config.scheduler_timezone)
        self.tasks_config: Optional[TasksConfiguration] = None
        self.config_file_hash: Optional[str] = None
        self.running = False
        self.loaded_task_ids: set = set()

        logger.debug(
            f"Scheduler service initialized with timezone: {config.scheduler_timezone}"
        )

    def is_enabled(self) -> bool:
        """Check if the scheduler is enabled."""
        return config.scheduler_enabled

    def _get_config_file_path(self) -> Path:
        """Get the path to the task configuration file."""
        return Path(config.tasks_config_path)

    def _get_config_file_hash(self) -> Optional[str]:
        """Get the SHA256 hash of the configuration file content."""
        config_file = self._get_config_file_path()
        if config_file.exists():
            try:
                with open(config_file, "rb") as f:
                    content = f.read()
                return hashlib.sha256(content).hexdigest()
            except Exception as e:
                logger.warning(f"Error reading config file for hash: {e}")
                return None
        return None

    def _load_tasks_configuration(self) -> Optional[TasksConfiguration]:
        """Load tasks configuration from file."""
        config_file = self._get_config_file_path()

        if not config_file.exists():
            logger.warning(f"Tasks configuration file not found: {config_file}")
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Update last_modified timestamp
            if "last_modified" not in data:
                data["last_modified"] = now_local_isoformat()

            tasks_config = TasksConfiguration(**data)
            logger.info(
                f"Loaded {len(tasks_config.tasks)} tasks from configuration file"
            )
            return tasks_config

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in tasks configuration file: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading tasks configuration: {e}")
            return None

    def _should_reload_config(self) -> bool:
        """Check if the configuration file has been modified and should be reloaded."""
        if not self.tasks_config:
            logger.debug("No tasks config loaded, should reload")
            return True

        current_hash = self._get_config_file_hash()

        if current_hash is None:
            logger.debug("Config file doesn't exist or can't be read, not reloading")
            return False

        # Check if content hash has changed
        if self.config_file_hash is None or current_hash != self.config_file_hash:
            logger.debug(
                f"Config file content changed: {self.config_file_hash[:8] if self.config_file_hash else 'None'}... -> {current_hash[:8]}..."
            )
            return True

        logger.debug(f"Config file unchanged: hash={current_hash[:8]}...")
        return False

    def _clear_existing_jobs(self) -> None:
        """Remove all existing scheduled jobs."""
        for job_id in list(self.loaded_task_ids):
            try:
                self.scheduler.remove_job(job_id)
                logger.debug(f"Removed job: {job_id}")
            except Exception as e:
                logger.warning(f"Error removing job {job_id}: {e}")

        self.loaded_task_ids.clear()

    def _schedule_task(self, task: TaskConfig) -> bool:
        """Schedule a single task with APScheduler."""
        try:
            if not task.enabled:
                logger.debug(f"Skipping disabled task: {task.id}")
                return False

            # Create trigger based on schedule type
            if task.schedule.type == "cron":
                if not task.schedule.expression:
                    logger.error(
                        f"Task {task.id}: Cron expression is required for cron schedule"
                    )
                    return False

                # Parse cron expression (format: minute hour day month day_of_week)
                cron_parts = task.schedule.expression.split()
                if len(cron_parts) != 5:
                    logger.error(
                        f"Task {task.id}: Invalid cron expression format: {task.schedule.expression}"
                    )
                    return False

                trigger = CronTrigger(
                    minute=cron_parts[0],
                    hour=cron_parts[1],
                    day=cron_parts[2],
                    month=cron_parts[3],
                    day_of_week=cron_parts[4],
                    timezone=config.scheduler_timezone,
                )

            elif task.schedule.type == "interval":
                if not task.schedule.interval_seconds:
                    logger.error(
                        f"Task {task.id}: Interval seconds is required for interval schedule"
                    )
                    return False

                trigger = IntervalTrigger(
                    seconds=task.schedule.interval_seconds,
                    timezone=config.scheduler_timezone,
                )

            elif task.schedule.type == "date":
                # One-time date-based task
                if not task.schedule.run_at:
                    logger.error(
                        f"Task {task.id}: run_at is required for date schedule"
                    )
                    return False

                run_at = ensure_timezone(task.schedule.run_at)
                # Convert to scheduler timezone to avoid surprises
                run_at = run_at.astimezone(get_scheduler_timezone())

                trigger = DateTrigger(
                    run_date=run_at, timezone=config.scheduler_timezone
                )

            else:
                logger.error(  # type: ignore[unreachable]
                    f"Task {task.id}: Unknown schedule type: {task.schedule.type}"
                )
                return False

            # Add job to scheduler
            self.scheduler.add_job(
                func=self._execute_task_wrapper,
                trigger=trigger,
                args=[task],
                id=task.id,
                name=task.name,
                max_instances=1,  # Prevent overlapping executions
                misfire_grace_time=(
                    config.one_time_task_misfire_grace_seconds
                    if task.schedule.type == "date"
                    else 60
                ),
                coalesce=True,  # Coalesce missed executions
            )

            self.loaded_task_ids.add(task.id)
            logger.info(
                f"Scheduled task '{task.name}' ({task.id}) with {task.schedule.type} schedule"
            )
            return True

        except Exception as e:
            logger.error(f"Error scheduling task {task.id}: {e}")
            return False

    async def _execute_task_wrapper(self, task: TaskConfig) -> None:
        """Wrapper function for task execution that handles errors and logging."""
        try:
            logger.info(
                f"Starting scheduled execution of task '{task.name}' ({task.id})"
            )
            result = await task_manager.execute_task(task)

            if result.success:
                logger.info(f"Task '{task.name}' completed successfully")
            else:
                logger.warning(
                    f"Task '{task.name}' completed with errors: {result.error_message}"
                )

        except Exception as e:
            logger.error(f"Unexpected error executing task '{task.name}': {e}")
        finally:
            # For one-time tasks, perform cleanup after execution attempt
            try:
                if task.schedule.type == "date":
                    self._cleanup_one_time_task(task.id)
            except Exception as cleanup_err:
                logger.error(
                    f"Failed to cleanup one-time task {task.id}: {cleanup_err}"
                )

    def _cleanup_one_time_task(self, task_id: str) -> None:
        """Cleanup a one-time task from the config file after it runs."""
        config_file = self._get_config_file_path()
        if not config_file.exists():
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            original_count = len(data.get("tasks", []))
            if config.one_time_task_cleanup_mode == "remove":
                data["tasks"] = [
                    t for t in data.get("tasks", []) if t.get("id") != task_id
                ]
            else:
                for t in data.get("tasks", []):
                    if t.get("id") == task_id:
                        t["enabled"] = False

            # Update last_modified
            data["last_modified"] = now_local_isoformat()

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Reload scheduler to reflect changes
            if (
                original_count != len(data.get("tasks", []))
                or config.one_time_task_cleanup_mode != "remove"
            ):
                self.reload_configuration()

        except Exception as e:
            logger.error(f"Error cleaning up one-time task {task_id}: {e}")

    def reload_configuration(self) -> bool:
        """Reload task configuration and reschedule tasks."""
        logger.info("Reloading task configuration...")

        # Load new configuration
        new_config = self._load_tasks_configuration()
        if not new_config:
            logger.error("Failed to load task configuration")
            return False

        # Update file content hash
        self.config_file_hash = self._get_config_file_hash()

        # Clear existing jobs
        self._clear_existing_jobs()

        # Schedule new tasks
        scheduled_count = 0
        for task in new_config.tasks:
            if self._schedule_task(task):
                scheduled_count += 1

        self.tasks_config = new_config

        logger.info(
            f"Configuration reloaded: {scheduled_count}/{len(new_config.tasks)} tasks scheduled"
        )
        return True

    def _config_reload_check(self) -> None:
        """Periodic check for configuration file changes."""
        try:
            logger.debug("Checking for configuration file changes...")
            if self._should_reload_config():
                logger.info("Configuration file changed, reloading...")
                self.reload_configuration()
            else:
                logger.debug("No configuration changes detected")
        except Exception as e:
            logger.error(f"Error during configuration reload check: {e}")

    def start(self) -> None:
        """Start the scheduler service."""
        if not self.is_enabled():
            logger.info("Scheduler is disabled, not starting")
            return

        if self.running:
            logger.warning("Scheduler service is already running")
            return

        logger.info("Starting scheduler service...")

        try:
            # Load initial configuration
            if not self.reload_configuration():
                logger.error(
                    "Failed to load initial configuration, scheduler not started"
                )
                return

            # Schedule periodic configuration reload check
            self.scheduler.add_job(
                func=self._config_reload_check,
                trigger=IntervalTrigger(seconds=config.task_config_reload_interval),
                id="config_reload_check",
                name="Configuration Reload Check",
                max_instances=1,
            )

            # Start the scheduler
            self.scheduler.start()
            self.running = True

            logger.info(
                f"Scheduler service started with {len(self.loaded_task_ids)} tasks, "
                f"config reload every {config.task_config_reload_interval}s"
            )

        except Exception as e:
            logger.error(f"Failed to start scheduler service: {e}")
            self.running = False

    def stop(self) -> None:
        """Stop the scheduler service."""
        if not self.running:
            return

        logger.info("Stopping scheduler service...")

        try:
            self.scheduler.shutdown(wait=True)
            self.running = False
            self.loaded_task_ids.clear()
            logger.info("Scheduler service stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler service: {e}")

    def get_scheduled_jobs(self) -> List[Dict]:
        """Get information about currently scheduled jobs."""
        if not self.running:
            return []

        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat()
                    if job.next_run_time
                    else None,
                    "trigger": str(job.trigger),
                    "func": job.func.__name__
                    if hasattr(job.func, "__name__")
                    else str(job.func),
                }
            )

        return jobs_info

    def get_status(self) -> Dict:
        """Get scheduler service status."""
        return {
            "enabled": self.is_enabled(),
            "running": self.running,
            "timezone": config.scheduler_timezone,
            "config_file": str(self._get_config_file_path()),
            "config_file_exists": self._get_config_file_path().exists(),
            "config_file_hash": self.config_file_hash[:16]
            if self.config_file_hash
            else None,
            "reload_interval": config.task_config_reload_interval,
            "loaded_tasks": len(self.loaded_task_ids),
            "scheduled_jobs": len(self.scheduler.get_jobs()) if self.running else 0,
        }


# Create a global scheduler service instance
scheduler_service = SchedulerService()
