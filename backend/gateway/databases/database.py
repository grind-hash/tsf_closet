"""SQLite database module for session and history persistence.

This module provides async database operations using aiosqlite.
Schema management is handled by Alembic migrations.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

import aiosqlite

if TYPE_CHECKING:
    from aiosqlite import Connection

logger = logging.getLogger(__name__)

# Database connection singleton
_connection: Connection | None = None

# Default database path for sync connections
_db_path: Path | None = None


def get_db_connection() -> sqlite3.Connection:
    """Get a synchronous database connection.

    Used by gallery.py and achievements.py for simple sync queries.

    Returns:
        A sqlite3 connection.
    """
    global _db_path
    if _db_path is None:
        from ..settings.config import settings

        _db_path = settings.database_path

    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    return conn


async def init_database(db_path: Path) -> Connection:
    """Initialize the database connection.

    Note: Schema creation is handled by Alembic migrations.
    Run `alembic upgrade head` before starting the application.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The database connection.
    """
    global _connection

    if _connection is not None:
        return _connection

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing database at {db_path}")
    _connection = await aiosqlite.connect(db_path)
    _connection.row_factory = aiosqlite.Row

    # Enable foreign keys
    await _connection.execute("PRAGMA foreign_keys = ON")

    logger.info("Database initialized successfully")
    return _connection


async def get_connection() -> Connection:
    """Get the database connection.

    Returns:
        The database connection.

    Raises:
        RuntimeError: If the database is not initialized.
    """
    if _connection is None:
        raise RuntimeError("Database not initialized. Call init_database first.")
    return _connection


async def close_database() -> None:
    """Close the database connection."""
    global _connection

    if _connection is not None:
        await _connection.close()
        _connection = None
        logger.info("Database connection closed")


@asynccontextmanager
async def transaction() -> AsyncGenerator[Connection, None]:
    """Context manager for database transactions.

    Usage:
        async with transaction() as conn:
            await conn.execute(...)
            # Commits on success, rolls back on exception
    """
    conn = await get_connection()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
