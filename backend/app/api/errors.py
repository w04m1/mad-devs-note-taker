from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        field_errors: dict[str, str] | None = None,
        current: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors
        self.current = current


def body(
    code: str,
    message: str,
    field_errors: dict[str, str] | None = None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"code": code, "message": message, "field_errors": field_errors, "current": current}


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        content=body(exc.code, exc.message, exc.field_errors, exc.current),
        status_code=exc.status_code,
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        fields[location or "request"] = error["msg"]
    return JSONResponse(
        content=body("validation_error", "Request validation failed", fields), status_code=422
    )


async def stale_error_handler(_request: Request, _exc: StaleDataError) -> JSONResponse:
    return JSONResponse(
        content=body("version_conflict", "The resource changed concurrently"), status_code=409
    )
