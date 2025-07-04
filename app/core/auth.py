from fastapi import Header, HTTPException

from app.core.settings import config


async def verify_token(x_token: str = Header()):
    if x_token != config.x_token:
        raise HTTPException(status_code=400, detail="X-Token header invalid")
