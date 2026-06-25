"""Knowledge sync pipeline — Phase 6.

Workflow:
  1. Fetch AWS What's New RSS feed
  2. Identify affected services
  3. For each service, search documentation via MCP
  4. Read each result page via MCP
  5. Compute SHA-256 hash
  6. If hash differs from cached value → upsert
  7. If unchanged → skip

Schedule: daily at 02:00 UTC via APScheduler.
Trigger manually: POST /admin/sync
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.logging import get_logger
from services.sync.whats_new import fetch_whats_new, items_to_service_updates

if TYPE_CHECKING:
    from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)

_SEARCH_LIMIT = 5  # docs per service to check
_READ_TOP_N = 3  # docs per service to actually read and cache


@dataclasses.dataclass
class SyncResult:
    services_checked: int = 0
    pages_checked: int = 0
    pages_updated: int = 0
    pages_skipped: int = 0
    errors: int = 0


async def run_sync(mcp_tools: AWSDocsMCPTools, db_available: bool = True) -> SyncResult:
    """Execute one full sync cycle. Safe to call from the scheduler or an API endpoint."""
    result = SyncResult()

    # ── Step 1: Fetch What's New ──────────────────────────────────────
    try:
        items = await fetch_whats_new(limit=20)
    except Exception as exc:
        logger.error("Failed to fetch What's New feed", extra={"error": str(exc)})
        result.errors += 1
        return result

    updates = items_to_service_updates(items)
    result.services_checked = len(updates)

    if not updates:
        logger.info("No service updates found — sync complete")
        return result

    # ── Step 2–6: Search, read, hash, upsert per service ─────────────
    from services.cache.models import DocCache  # noqa: PLC0415
    from services.cache.repository import DocCacheRepository

    if db_available:
        from core.database import _session_factory  # noqa: PLC0415
    else:
        _session_factory = None

    for update in updates:
        logger.info("Syncing service", extra={"service": update.service_name})

        # Search for docs related to this service
        try:
            search_results = await mcp_tools.search_documentation(
                f"Amazon {update.service_name} documentation guide", limit=_SEARCH_LIMIT
            )
        except Exception as exc:
            logger.error("Search failed", extra={"service": update.service_name, "error": str(exc)})
            result.errors += 1
            continue

        top_results = [r for r in search_results if r.url][:_READ_TOP_N]

        for search_result in top_results:
            url = search_result.url
            result.pages_checked += 1

            try:
                doc = await mcp_tools.read_documentation(url, max_length=8000)
            except Exception as exc:
                logger.error("Read failed", extra={"url": url, "error": str(exc)})
                result.errors += 1
                continue

            new_hash = DocCache.compute_hash(doc.content)

            # Skip DB write if no session factory (DB not configured)
            if _session_factory is None:
                logger.info("DB not available — skipping cache write", extra={"url": url})
                result.pages_skipped += 1
                continue

            async with _session_factory() as session:
                repo = DocCacheRepository(session)
                existing = await repo.get(url)

                if existing and existing.hash == new_hash:
                    logger.info("Content unchanged — skipping", extra={"url": url})
                    result.pages_skipped += 1
                else:
                    await repo.upsert(
                        url=url,
                        title=doc.title or search_result.title,
                        content=doc.content,
                    )
                    logger.info("Cache updated", extra={"url": url})
                    result.pages_updated += 1

                    # Index into Qdrant if available
                    try:
                        from services.vector.client import _client as qdrant_client  # noqa: PLC0415
                        from services.vector.indexer import index_document  # noqa: PLC0415

                        if qdrant_client is not None:
                            await index_document(
                                url=url,
                                title=doc.title or search_result.title,
                                content=doc.content,
                                doc_hash=new_hash,
                            )
                    except Exception as exc:
                        logger.warning(
                            "Qdrant indexing skipped", extra={"url": url, "error": str(exc)}
                        )

    logger.info(
        "Sync complete",
        extra=dataclasses.asdict(result),
    )
    return result


# ── APScheduler setup ─────────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


def create_scheduler(mcp_tools: AWSDocsMCPTools, db_available: bool = True) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler (not yet started)."""

    async def _job() -> None:
        logger.info("Scheduled sync starting")
        await run_sync(mcp_tools, db_available=db_available)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="daily_knowledge_sync",
        name="Daily AWS Docs Knowledge Sync",
        replace_existing=True,
        misfire_grace_time=3600,  # tolerate up to 1h delay
    )
    return scheduler


def start_scheduler(mcp_tools: AWSDocsMCPTools, db_available: bool = True) -> AsyncIOScheduler:
    """Create, start, and return the scheduler. Store globally for shutdown."""
    global _scheduler
    _scheduler = create_scheduler(mcp_tools, db_available=db_available)
    _scheduler.start()
    logger.info("Sync scheduler started — next run at 02:00 UTC daily")
    return _scheduler


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Sync scheduler stopped")
    _scheduler = None
