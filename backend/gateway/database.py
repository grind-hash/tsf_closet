"""SQLite database module for session and history persistence.

This module provides async database operations using aiosqlite.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

import aiosqlite

if TYPE_CHECKING:
    from aiosqlite import Connection

logger = logging.getLogger(__name__)

# Database connection singleton
_connection: Connection | None = None


SCHEMA_SQL = """
-- ユーザーテーブル
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- デフォルトユーザー作成
INSERT OR IGNORE INTO users (id) VALUES ('default-user');

-- セッションテーブル
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    character_id TEXT,
    current_image_path TEXT NOT NULL,
    transformation_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(user_id, is_active);

-- 履歴テーブル
CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    instruction TEXT NOT NULL,
    image_path TEXT NOT NULL,
    feeling_text TEXT,
    before_description TEXT,
    after_description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_session_id ON history(session_id);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(session_id, created_at);

-- セッション統計テーブル (T004)
CREATE TABLE IF NOT EXISTS session_stats (
    session_id TEXT PRIMARY KEY,
    excitement INTEGER NOT NULL DEFAULT 0,
    immersion INTEGER NOT NULL DEFAULT 50,
    challenge INTEGER NOT NULL DEFAULT 0,
    passed_critical_points TEXT NOT NULL DEFAULT '[]',
    difficulty TEXT NOT NULL DEFAULT 'normal',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 変身タグテーブル (T005)
CREATE TABLE IF NOT EXISTS transformation_tags (
    history_id TEXT PRIMARY KEY,
    costume_category TEXT NOT NULL DEFAULT 'other',
    sparkle_level TEXT NOT NULL DEFAULT 'medium',
    age_impression TEXT NOT NULL DEFAULT 'unknown',
    FOREIGN KEY (history_id) REFERENCES history(id) ON DELETE CASCADE
);

-- 達成エンディングテーブル (T006)
CREATE TABLE IF NOT EXISTS achieved_endings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ending_id TEXT NOT NULL,
    session_id TEXT,
    achieved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_achieved_endings_unique 
    ON achieved_endings(user_id, ending_id);
CREATE INDEX IF NOT EXISTS idx_achieved_endings_user 
    ON achieved_endings(user_id);

-- 会話テーブル (Conversation)
CREATE TABLE IF NOT EXISTS conversation (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'character'
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversation_session_id ON conversation(session_id);
CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation(session_id, created_at);

-- セッション属性テーブル (カスタム属性付与機能)
CREATE TABLE IF NOT EXISTS session_attributes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    attribute_text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_attributes_session_id ON session_attributes(session_id);
"""


async def init_database(db_path: Path) -> Connection:
    """Initialize the database connection and create schema.

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

    # Execute schema
    await _connection.executescript(SCHEMA_SQL)
    await _connection.commit()

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
