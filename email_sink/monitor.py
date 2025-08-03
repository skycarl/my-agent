"""
Email monitoring service with configurable routing to internal API endpoints.
"""

import asyncio
from typing import List
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.core.settings import config
from .email_client import EmailClient
from .parser import EmailParser
from .models import EmailAlert, EmailSinkConfig, AlertRequest


class EmailMonitorService:
    """Service that monitors email and routes alerts to internal API endpoints."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.email_configs: List[EmailSinkConfig] = []
        self.running = False

        # Load email sink configurations
        self._load_email_configs()

        logger.info(
            f"Email monitor service initialized with {len(self.email_configs)} sink configurations"
        )

    def _load_email_configs(self) -> None:
        """Load email sink configurations from environment settings."""
        self.email_configs = []

        # Parse sender patterns from config
        sender_patterns_str = config.email_sender_patterns.strip()
        if not sender_patterns_str:
            logger.warning("No email sender patterns configured")
            return

        # Split by comma and clean up whitespace
        patterns = [
            pattern.strip()
            for pattern in sender_patterns_str.split(",")
            if pattern.strip()
        ]

        if not patterns:
            logger.warning("No valid email sender patterns found after parsing")
            return

        # Create a config entry for each pattern
        for pattern in patterns:
            self.email_configs.append(
                EmailSinkConfig(
                    sender_pattern=pattern,
                    endpoint="/process_alert",  # All patterns route to process_alert for agent processing
                    description=f"Email alerts from pattern: {pattern}",
                )
            )

        logger.info(
            f"Loaded {len(self.email_configs)} email sink configurations: {patterns}"
        )

    async def check_email_for_alerts(self) -> None:
        """Check email for new alerts and route them to appropriate endpoints."""
        if not config.email_sink_enabled:
            logger.debug("Email sink is disabled, skipping check")
            return

        if not config.email_address or not config.email_password:
            logger.warning("Email credentials not configured, skipping email check")
            return

        try:
            with EmailClient() as email_client:
                # Check each configured email sink
                for sink_config in self.email_configs:
                    await self._process_sink_config(email_client, sink_config)

        except Exception as e:
            logger.error(f"Error during email check: {e}")

    async def _process_sink_config(
        self, email_client: EmailClient, sink_config: EmailSinkConfig
    ) -> None:
        """Process emails for a specific sink configuration."""
        try:
            logger.debug(
                f"Checking for emails from pattern: {sink_config.sender_pattern}"
            )

            # Get unread messages matching the sender pattern
            messages = email_client.get_unread_messages_from_sender(
                sink_config.sender_pattern
            )

            if not messages:
                return

            logger.info(
                f"Processing {len(messages)} messages for {sink_config.description}"
            )

            for uid, raw_message in messages:
                try:
                    # Parse the email
                    alert = EmailParser.parse_raw_message(uid, raw_message)
                    if not alert:
                        logger.warning(f"Failed to parse message {uid}")
                        continue

                    # Post to the configured endpoint
                    success = await self._post_alert_to_endpoint(
                        alert, sink_config.endpoint
                    )

                    if success:
                        # Mark as read only if successfully processed
                        email_client.mark_as_read(uid)
                        logger.info(f"Successfully processed and marked as read: {uid}")
                    else:
                        logger.warning(
                            f"Failed to process alert {uid}, leaving as unread"
                        )

                except Exception as e:
                    logger.error(f"Error processing message {uid}: {e}")

        except Exception as e:
            logger.error(f"Error processing sink config {sink_config.description}: {e}")

    async def _post_alert_to_endpoint(self, alert: EmailAlert, endpoint: str) -> bool:
        """
        Post an alert to the specified internal API endpoint.

        Args:
            alert: EmailAlert object
            endpoint: API endpoint path (e.g., "/commute_alert")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build the full URL - use app_url from config
            base_url = config.app_url.rstrip("/")
            full_url = f"{base_url}{endpoint}"

            # Create the request payload
            alert_request = AlertRequest(
                uid=alert.uid,
                subject=alert.subject,
                body=alert.body,
                sender=alert.sender,
                date=alert.date,
                alert_type="email",
            )

            # Make the POST request
            headers = {
                "Content-Type": "application/json",
                "X-Token": config.x_token,  # Use the same auth token as other services
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    full_url,
                    json=alert_request.model_dump(mode="json"),
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code in [200, 201]:
                    logger.debug(f"Successfully posted alert to {endpoint}")
                    return True
                else:
                    logger.error(
                        f"Failed to post alert to {endpoint}: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error posting alert to {endpoint}: {e}")
            return False

    def start(self) -> None:
        """Start the email monitoring service."""
        if self.running:
            logger.warning("Email monitor service is already running")
            return

        if not config.email_sink_enabled:
            logger.info("Email sink is disabled, not starting monitor service")
            return

        logger.info("Starting email monitoring service...")

        # Schedule the email check job
        self.scheduler.add_job(
            self.check_email_for_alerts,
            "interval",
            seconds=config.email_poll_interval,
            id="email_check",
            max_instances=1,  # Prevent overlapping executions
        )

        self.scheduler.start()
        self.running = True

        logger.info(
            f"Email monitoring service started, checking every {config.email_poll_interval} seconds"
        )

    def stop(self) -> None:
        """Stop the email monitoring service."""
        if not self.running:
            return

        logger.info("Stopping email monitoring service...")
        self.scheduler.shutdown()
        self.running = False
        logger.info("Email monitoring service stopped")

    async def run_forever(self) -> None:
        """Run the service indefinitely."""
        self.start()

        try:
            # Keep the service running
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()


# Global service instance
_monitor_service = None


def get_monitor_service() -> EmailMonitorService:
    """Get the global email monitor service instance."""
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = EmailMonitorService()
    return _monitor_service
