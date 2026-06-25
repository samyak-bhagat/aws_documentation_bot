"""Admin endpoints.

POST /admin/sync     — trigger knowledge sync pipeline
POST /admin/reindex  — re-index all doc_cache entries into OpenSearch
"""

import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.logging import get_logger
from services.auth.jwt import TokenPayload, get_admin_user
from services.sync.scheduler import run_sync

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger(__name__)


class SyncResponse(BaseModel):
    status: str
    services_checked: int
    pages_checked: int
    pages_updated: int
    pages_skipped: int
    errors: int


class ReindexResponse(BaseModel):
    status: str
    total: int
    chunks: int
    errors: int


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    request: Request,
    _admin: TokenPayload = Depends(get_admin_user),  # noqa: B008
) -> SyncResponse:
    """Manually trigger the knowledge sync pipeline (no auth required in dev)."""
    mcp_tools = getattr(request.app.state, "mcp_tools", None)
    if mcp_tools is None:
        raise HTTPException(status_code=503, detail="MCP not connected — cannot run sync.")

    db_available = getattr(request.app.state, "db_available", False)
    logger.info("Manual sync triggered via /admin/sync", extra={"db_available": db_available})
    result = await run_sync(mcp_tools, db_available=db_available)

    return SyncResponse(
        status="ok",
        **dataclasses.asdict(result),
    )


@router.post("/reindex", response_model=ReindexResponse)
async def trigger_reindex(
    request: Request,
    _admin: TokenPayload = Depends(get_admin_user),  # noqa: B008
) -> ReindexResponse:
    """Re-index all cached docs from PostgreSQL into OpenSearch."""
    if not getattr(request.app.state, "db_available", False):
        raise HTTPException(status_code=503, detail="PostgreSQL not available.")
    if not getattr(request.app.state, "vector_available", False):
        raise HTTPException(status_code=503, detail="Vector store not available.")

    from core.database import _session_factory
    from services.vector.indexer import index_all_cached

    if _session_factory is None:
        raise HTTPException(status_code=503, detail="DB session factory not ready.")

    logger.info("Manual reindex triggered via /admin/reindex")
    async with _session_factory() as session:
        stats = await index_all_cached(session)

    return ReindexResponse(status="ok", **stats)
