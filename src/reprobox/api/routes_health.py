"""Health check endpoint decoupled from database state."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health() -> JSONResponse:
    """Return static healthy response without touching the database."""
    return JSONResponse(status_code=200, content={"status": "ok"})
