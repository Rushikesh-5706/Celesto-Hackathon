"""FastAPI application factory and lifecycle management."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from reprobox.api.errors import generic_400_handler, validation_exception_handler
from reprobox.api.routes_health import router as health_router
from reprobox.api.routes_jobs import router as jobs_router
from reprobox.api.routes_reports import router as reports_router
from reprobox.api.routes_runs import router as runs_router
from reprobox.ledger.database import apply_seed_sql, close_pool, wait_for_db
from reprobox.sandbox.lifecycle import install_cleanup_handlers
from reprobox.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger.info("Initializing Reprobox API control plane...")

    if threading.current_thread() is threading.main_thread():
        install_cleanup_handlers()

    seed_file = Path(__file__).resolve().parents[3] / "seeds" / "01_runs.sql"
    if not seed_file.exists():
        seed_file = Path("/app/seeds/01_runs.sql")

    if settings.database_url:
        logger.info("Waiting for ledger database...")
        db_ready = wait_for_db(max_wait_s=60)
        if not db_ready:
            logger.error("Database was not reachable within 60s timeout.")
            sys.exit(1)

        logger.info("Database is ready. Applying schema seed...")
        try:
            apply_seed_sql(seed_file)
            logger.info("Schema seed applied successfully.")
        except Exception as exc:
            logger.error("Failed to apply seed SQL: %s", exc)
            sys.exit(1)

    yield
    logger.info("Shutting down Reprobox API control plane...")
    close_pool()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Reprobox Control Plane",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(ValueError, generic_400_handler)

    app.include_router(health_router)
    app.include_router(runs_router)
    app.include_router(jobs_router)
    app.include_router(reports_router)

    return app


app = create_app()
