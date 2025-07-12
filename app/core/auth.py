from fastapi import Header, HTTPException
from loguru import logger

from app.core.settings import config

logger.debug("Auth module loaded")


async def verify_token(x_token: str = Header(alias="X-Token")):
    """Verify the X-Token header for authentication."""
    
    if x_token != config.x_token:
        logger.warning("Authentication failed: token mismatch")
        raise HTTPException(status_code=400, detail="X-Token header invalid")
    
    logger.debug("Authentication successful")
