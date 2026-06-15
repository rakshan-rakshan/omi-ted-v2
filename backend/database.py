"""Async SQLAlchemy engine + session. SQLite local, Postgres prod via DATABASE_URL.

Provides:
- engine, AsyncSessionLocal, get_session — async DB access
- Vector SQLAlchemy type — works in both SQLite (JSON) and Postgres (pgvector)
"""
from __future__ import annotations

import json
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import Text, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

_raw_db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
# Railway sets postgresql://, SQLAlchemy asyncpg needs postgresql+asyncpg://
if _raw_db_url.startswith("postgresql://"):
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL = _raw_db_url

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base. All ORM models inherit this."""


class Vector(TypeDecorator):
    """SQLite-compatible Vector type. Stores as JSON in SQLite, pgvector in Postgres.

    Usage:
        embedding = mapped_column(Vector(768), nullable=True)
    """
    impl = Text
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector as PgVector
            except ImportError:
                raise ImportError("pgvector package required for PostgreSQL. pip install pgvector")
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value, dialect):
        if dialect.name == "sqlite":
            return json.dumps(value) if value is not None else None
        return value

    def process_result_value(self, value, dialect):
        if dialect.name == "sqlite":
            return json.loads(value) if value is not None else None
        return value


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Yields a session, closes on exit."""
    async with AsyncSessionLocal() as session:
        yield session
