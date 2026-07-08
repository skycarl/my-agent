from fastapi import Header, HTTPException
from loguru import logger

from app.core.settings import config

logger.debug("Auth module loaded")


async def verify_token(x_token: str = Header(alias="X-Token")):
    """Verify the X-Token header for authentication."""

    if not config.x_token:
        # Fail closed: without a configured token, no shared secret exists,
        # so nothing could authenticate legitimately anyway.
        logger.error("X_TOKEN is not configured; rejecting request")
        raise HTTPException(
            status_code=503, detail="Server authentication token is not configured"
        )

    if x_token != config.x_token:
        logger.warning("Authentication failed: token mismatch")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    logger.debug("Authentication successful")
