"""Custom error types and HTTP exception mappings."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map FastAPI and Pydantic validation errors to HTTP 400 with structured detail."""
    raw_errors: list[dict[str, Any]] = []
    if isinstance(exc, RequestValidationError | ValidationError):
        raw_errors = exc.errors()

    formatted: list[dict[str, str]] = []
    for err in raw_errors:
        loc = err.get("loc", ())
        field = ".".join(str(item) for item in loc) if loc else "request"
        msg = err.get("msg", "Validation error")
        formatted.append({"field": field, "message": msg})

    if not formatted:
        formatted.append({"field": "request", "message": str(exc)})

    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": formatted},
    )


async def generic_400_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map ValueError to HTTP 400 with structured detail."""
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": [{"field": "request", "message": str(exc)}]},
    )
