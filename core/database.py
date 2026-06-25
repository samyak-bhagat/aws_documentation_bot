"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    if not url:
        raise ValueError("DATABASE_URL is not set. Configure it in .env for Phase 5+.")
    return create_async_engine(url, echo=False, pool_pre_ping=True)


# Module-level engine and session factory — initialised lazily via init_db()
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str | None = None) -> None:
    """Create tables and initialise the session factory. Call once on startup."""
    global _engine, _session_factory

    _engine = _make_engine(database_url)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # Import models so their tables are registered with Base.metadata
    import services.auth.models  # noqa: F401
    import services.cache.models  # noqa: F401
    import services.memory.models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialised")


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with _session_factory() as session:
        yield session
