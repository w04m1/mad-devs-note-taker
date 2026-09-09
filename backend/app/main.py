from fastapi import FastAPI, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.api.errors import (
    ApiError,
    api_error_handler,
    stale_error_handler,
    validation_error_handler,
)
from app.api.router import router
from app.db.session import async_engine

app = FastAPI(title="Notetaker API", version="0.1.0")
app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(StaleDataError, stale_error_handler)  # type: ignore[arg-type]
app.include_router(router)


@app.get("/api/v1/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
async def ready(response: Response) -> dict[str, str]:
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
