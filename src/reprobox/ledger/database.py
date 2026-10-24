"""Database connection handling and schema initialization."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from reprobox.settings import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_pool(database_url: str | None = None) -> ConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        url = database_url or settings.database_url
        _pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.close()
        _pool = None


@contextmanager
def get_connection(database_url: str | None = None) -> Generator[psycopg.Connection, None, None]:
    pool = get_pool(database_url)
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def wait_for_db(max_wait_s: int = 60, database_url: str | None = None) -> bool:
    url = database_url or settings.database_url
    start = time.monotonic()
    delay = 0.5
    while time.monotonic() - start < max_wait_s:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception as exc:
            logger.debug("Database not ready yet (%s), retrying in %.1fs", exc, delay)
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)
    return False


def apply_seed_sql(seed_path: Path, database_url: str | None = None) -> None:
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed SQL file not found: {seed_path}")

    sql_text = seed_path.read_text(encoding="utf-8")
    with get_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute(sql_text)
    logger.info("Applied seed SQL from %s", seed_path)
