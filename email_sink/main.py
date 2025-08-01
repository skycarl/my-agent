"""
Main entry point for the email sink service.
"""

import asyncio
from loguru import logger

from app.core.logger import init_logging
from app.core.settings import config
from .monitor import get_monitor_service

# Initialize logging
init_logging()


async def main():
    """Main function for the email sink service."""
    logger.info("Starting Email Sink Service...")

    if not config.email_sink_enabled:
        logger.info("Email sink is disabled in configuration")
        return

    if not config.email_address or not config.email_password:
        logger.error(
            "Email credentials not configured. Please set EMAIL_ADDRESS and EMAIL_PASSWORD"
        )
        return

    # Get the monitor service and run it
    monitor_service = get_monitor_service()

    try:
        await monitor_service.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down email sink service...")
    except Exception as e:
        logger.error(f"Email sink service error: {e}")
    finally:
        monitor_service.stop()
        logger.info("Email sink service stopped")


if __name__ == "__main__":
    asyncio.run(main())
