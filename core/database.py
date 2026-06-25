"""Async SQLAlchemy engine, session factory, and Alembic migrations."""

from collections.abc import AsyncGenerator
from pathlib import Path

from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from alembic import command
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    if not url:
        raise ValueError("DATABASE_URL is not set")
    return create_async_engine(url, echo=False, pool_pre_ping=True)


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _run_migrations() -> None:
    """Apply Alembic migrations up to head."""
    if not ALEMBIC_INI.exists():
        raise FileNotFoundError(f"Alembic config not found: {ALEMBIC_INI}")
    alembic_cfg = Config(str(ALEMBIC_INI))
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)

    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    legacy_tables = {"aws_docs_cache", "chat_sessions", "users", "chat_messages"}
    if legacy_tables.issubset(tables) and "alembic_version" not in tables:
        command.stamp(alembic_cfg, "head")
        logger.info("Existing schema detected — stamped Alembic head")
        return

    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied")


async def init_db(database_url: str | None = None) -> None:
    """Run migrations and initialise the async session factory."""
    global _engine, _session_factory

    import services.auth.models  # noqa: F401
    import services.cache.models  # noqa: F401
    import services.memory.models  # noqa: F401

    _engine = _make_engine(database_url)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    _run_migrations()


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with _session_factory() as session:
        yield session
