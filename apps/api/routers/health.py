"""GET /health — liveness check."""

from fastapi import APIRouter, Request

from apps.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    mcp_connected: bool = getattr(request.app.state, "mcp_connected", False)
    return HealthResponse(status="ok", mcp_connected=mcp_connected)
