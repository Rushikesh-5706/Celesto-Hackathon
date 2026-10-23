"""Custom error types and HTTP exception mappings."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map FastAPI and Pydantic validation errors to HTTP 400."""
    errors: list[Any] = []
    if isinstance(exc, RequestValidationError | ValidationError):
        errors = exc.errors()
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": str(errors)},
    )


async def generic_400_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": str(exc)},
    )
