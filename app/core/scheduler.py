"""
Task scheduler service with APScheduler integration and hot reload functionality.
"""

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from croniter import croniter
from filelock import FileLock
from loguru import logger

from app.core.settings import config
from app.core.task_manager import task_manager
from app.core.task_store import get_config_lock_path, _write_storage_file
from app.models.tasks import TaskConfig, TasksConfiguration
from app.core.timezone_utils import (
    now_local_isoformat,
    ensure_timezone,
    parse_datetime_in_scheduler_tz,
)


def remap_cron_day_of_week(field: str) -> str:
    """Convert a standard-cron day-of-week field to APScheduler day names.

    Standard cron uses 0=Sun..6=Sat (7=Sun); APScheduler uses 0=Mon..6=Sun.
    Numeric expressions (values, lists, ranges, steps) are expanded into
    explicit day-name lists, since a converted range like 0-2 (sun-tue) is
    not a valid APScheduler range. Fields without digits (names, *) pass
    through unchanged.
    """
    if not re.search(r"\d", field):
        return field

    names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
    out: list[str] = []
    for part in field.split(","):
        if not re.search(r"\d", part):
            out.append(part)
            continue
        expr, _, step_str = part.partition("/")
        step = int(step_str) if step_str else 1
        if expr == "*":
            low, high = 0, 6
        elif "-" in expr:
            low_str, high_str = expr.split("-", 1)
            low, high = int(low_str), int(high_str)
            if low > high:
                # Wrap-around range (e.g. 6-0 = Sat-Sun): unwrap past the
                # week boundary; names[day % 7] folds it back
                high += 7
        else:
            low = high = int(expr)
        out.extend(names[day % 7] for day in range(low, high + 1, step))

    # Dedupe while preserving order (e.g. "0,7" both mean Sunday)
    return ",".join(dict.fromkeys(out))


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
            logger.info(
                f"Tasks configuration file not found, starting with empty task list: {config_file}"
            )
            return TasksConfiguration()

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

        return False

    def _clear_existing_jobs(self) -> None:
        """Remove all existing scheduled jobs."""
        for job_id in list(self.loaded_task_ids):
            try:
                job = self.scheduler.get_job(job_id)
                if job is None:
                    # Common for one-time jobs: APScheduler auto-removes them after execution
                    logger.debug(f"Job not found (already removed): {job_id}")
                    continue
                self.scheduler.remove_job(job_id)
                logger.debug(f"Removed job: {job_id}")
            except Exception as e:
                # Absence is expected for completed one-time jobs
                logger.debug(f"Non-critical error removing job {job_id}: {e}")

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

                if not croniter.is_valid(task.schedule.expression):
                    logger.error(
                        f"Task {task.id}: Invalid cron expression: {task.schedule.expression}"
                    )
                    return False

                remapped_dow = remap_cron_day_of_week(cron_parts[4])

                trigger = CronTrigger(
                    minute=cron_parts[0],
                    hour=cron_parts[1],
                    day=cron_parts[2],
                    month=cron_parts[3],
                    day_of_week=remapped_dow,
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

                # Same interpretation the write path uses (task_store), so a
                # hand-edited naive run_at doesn't fire at a different wall
                # clock than the one the API would have scheduled.
                run_at = parse_datetime_in_scheduler_tz(task.schedule.run_at)

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
                    self._cleanup_one_time_task(task)
            except Exception as cleanup_err:
                logger.error(
                    f"Failed to cleanup one-time task {task.id}: {cleanup_err}"
                )

    def _cleanup_one_time_task(self, task: TaskConfig) -> None:
        """Cleanup a one-time task from the config file after it runs.

        `task` is the snapshot captured at schedule time. The stored task is
        re-checked before touching it: if the user edited it (e.g. to cron,
        or to a new run_at) while this execution was in flight, the edit is
        kept instead of being deleted/disabled.
        """
        config_file = self._get_config_file_path()
        if not config_file.exists():
            return

        try:
            with FileLock(get_config_lock_path()):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                current = next(
                    (t for t in data.get("tasks", []) if t.get("id") == task.id),
                    None,
                )
                if current is None:
                    return
                schedule = current.get("schedule", {}) or {}
                if schedule.get("type") != "date" or not self._same_run_at(
                    schedule.get("run_at"), task.schedule.run_at
                ):
                    logger.info(
                        f"Task {task.id} was edited since scheduling; skipping cleanup"
                    )
                    return

                original_count = len(data.get("tasks", []))
                if config.one_time_task_cleanup_mode == "remove":
                    data["tasks"] = [
                        t for t in data.get("tasks", []) if t.get("id") != task.id
                    ]
                else:
                    current["enabled"] = False

                # Update last_modified
                data["last_modified"] = now_local_isoformat()

                _write_storage_file(data)

            # Reload scheduler to reflect changes
            if (
                original_count != len(data.get("tasks", []))
                or config.one_time_task_cleanup_mode != "remove"
            ):
                self.reload_configuration()

        except Exception as e:
            logger.error(f"Error cleaning up one-time task {task.id}: {e}")

    @staticmethod
    def _same_run_at(stored_run_at, snapshot_run_at) -> bool:
        """Compare a stored ISO run_at string with the snapshot's datetime."""
        if not stored_run_at or snapshot_run_at is None:
            return True  # nothing to compare against; don't block cleanup
        try:
            stored = ensure_timezone(datetime.fromisoformat(str(stored_run_at)))
            return stored == ensure_timezone(snapshot_run_at)
        except ValueError:
            return False

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

    async def _config_reload_check(self) -> None:
        """Periodic check for configuration file changes.

        Async so APScheduler runs it on the event loop rather than a worker
        thread — reload_configuration mutates scheduler state that request
        handlers also touch, and must not run concurrently with them.
        """
        try:
            if self._should_reload_config():
                logger.info("Configuration file changed, reloading...")
                self.reload_configuration()
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
            # Load initial configuration. Start the scheduler even if this
            # fails (e.g. corrupt config file) so later successful reloads
            # actually run jobs.
            if not self.reload_configuration():
                logger.error(
                    "Failed to load initial configuration; starting scheduler "
                    "anyway so a later reload can recover"
                )

            # Schedule periodic configuration reload check
            self.scheduler.add_job(
                func=self._config_reload_check,
                trigger=IntervalTrigger(seconds=config.task_config_reload_interval),
                id="config_reload_check",
                name="Configuration Reload Check",
                max_instances=1,
            )

            # Schedule daily cleanups at 1:00 AM. The wrappers are async so
            # the jobs run on the event loop, not a worker thread — the
            # cleanup functions do read-modify-write on JSON files that
            # request handlers also touch, with no cross-thread locking.
            from app.agents.commute.preferences_service import (
                cleanup_expired_overrides,
            )
            from app.agents.commute.commute_service import cleanup_old_alerts

            async def _run_overrides_cleanup() -> None:
                cleanup_expired_overrides()

            async def _run_alerts_cleanup() -> None:
                cleanup_old_alerts()

            self.scheduler.add_job(
                func=_run_overrides_cleanup,
                trigger=CronTrigger(
                    hour=1, minute=0, timezone=config.scheduler_timezone
                ),
                id="commute_overrides_cleanup",
                name="Cleanup Expired Commute Overrides",
                max_instances=1,
            )

            self.scheduler.add_job(
                func=_run_alerts_cleanup,
                trigger=CronTrigger(
                    hour=1, minute=0, timezone=config.scheduler_timezone
                ),
                id="commute_alerts_cleanup",
                name="Cleanup Old Commute Alerts",
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


# Create a global scheduler service instance
scheduler_service = SchedulerService()
