from fastapi import FastAPI, APIRouter

from app.core.main_router import router as main_router
from app.core.logger import init_logging

root_router = APIRouter()

app = FastAPI(title="FastAPI Boiler Plate")

app.include_router(main_router)
app.include_router(root_router)

init_logging()

if __name__ == "__main__":
    # Use this for debugging purposes only
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
