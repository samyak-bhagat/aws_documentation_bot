"""DocCacheRepository — read/write AWS documentation pages to PostgreSQL."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger
from services.cache.models import DocCache

logger = get_logger(__name__)


class DocCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, url: str) -> DocCache | None:
        """Return a cached entry by URL, or None if not found."""
        result = await self._session.execute(select(DocCache).where(DocCache.url == url))
        return result.scalar_one_or_none()

    def is_fresh(self, entry: DocCache) -> bool:
        """Return True if the cached entry is within the TTL window."""
        ttl = timedelta(hours=settings.doc_cache_ttl_hours)
        age = datetime.now(UTC) - entry.last_fetched.replace(tzinfo=UTC)
        return age < ttl

    async def upsert(self, url: str, title: str, content: str) -> DocCache:
        """Insert or update a cache entry. Never deletes — marks deprecated instead."""
        content_hash = DocCache.compute_hash(content)
        now = datetime.now(UTC)

        stmt = (
            insert(DocCache)
            .values(
                url=url,
                title=title,
                content=content,
                hash=content_hash,
                last_fetched=now,
                last_checked=now,
                deprecated=False,
            )
            .on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "title": title,
                    "content": content,
                    "hash": content_hash,
                    "last_fetched": now,
                    "last_checked": now,
                    "deprecated": False,
                },
            )
            .returning(DocCache)
        )

        result = await self._session.execute(stmt)
        await self._session.commit()
        row = result.scalar_one()
        logger.info("Doc cache upserted", extra={"url": url, "hash": content_hash[:12]})
        return row

    async def mark_deprecated(self, url: str) -> None:
        """Mark a page as deprecated without deleting it."""
        entry = await self.get(url)
        if entry:
            entry.deprecated = True
            await self._session.commit()
