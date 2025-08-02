from fastapi import FastAPI, APIRouter
from contextlib import asynccontextmanager
from loguru import logger

from app.core.main_router import router as main_router
from app.core.logger import init_logging
from app.core.scheduler import scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting up application...")

    # Start the scheduler service
    try:
        scheduler_service.start()
        logger.info("Scheduler service startup completed")
    except Exception as e:
        logger.error(f"Failed to start scheduler service: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop the scheduler service
    try:
        scheduler_service.stop()
        logger.info("Scheduler service shutdown completed")
    except Exception as e:
        logger.error(f"Error stopping scheduler service: {e}")


root_router = APIRouter()

app = FastAPI(title="My agent backend", lifespan=lifespan)

app.include_router(main_router)
app.include_router(root_router)

init_logging()

if __name__ == "__main__":
    # Use this for debugging purposes only
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
