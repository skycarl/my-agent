import secrets

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

    # Constant-time comparison to avoid leaking the token via timing.
    # Compared as bytes: Starlette decodes headers as latin-1, and
    # compare_digest raises TypeError on non-ASCII str operands, which would
    # turn a bad token into an unhandled 500 instead of a 401.
    if not secrets.compare_digest(
        x_token.encode("utf-8"), config.x_token.encode("utf-8")
    ):
        logger.warning("Authentication failed: token mismatch")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    logger.debug("Authentication successful")
