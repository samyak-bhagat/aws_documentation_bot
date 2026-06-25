"""POST /admin/sync — manually trigger the knowledge sync pipeline."""

import dataclasses

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.logging import get_logger
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


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(request: Request) -> SyncResponse:
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
