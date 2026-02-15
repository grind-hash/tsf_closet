"""SQLAlchemy async engine and session configuration.

This module provides the async engine and session factory for database access.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..settings.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


DATABASE_URL = f"sqlite+aiosqlite:///{settings.database_path}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

sync_engine = create_engine(
    f"sqlite:///{settings.database_path}",
    echo=False,
    future=True,
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_session() -> Generator[Session, None, None]:
    """Get a sync database session for dependency injection."""
    with sync_session_factory() as session:
        yield session


async def init_db() -> None:
    """Initialize the database (create all tables).

    This should only be used for development/testing.
    Use Alembic migrations in production.
    """
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close the database connection."""
    await engine.dispose()
