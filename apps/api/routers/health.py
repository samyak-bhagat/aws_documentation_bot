"""GET /health — liveness and readiness checks."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from apps.api.schemas import HealthResponse

router = APIRouter()


def _build_health_response(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        mcp_connected=getattr(request.app.state, "mcp_connected", False),
        database_connected=getattr(request.app.state, "db_available", False),
        vector_store_connected=getattr(request.app.state, "vector_available", False),
        scheduler_running=getattr(request.app.state, "scheduler_running", False),
    )


def _is_ready(request: Request) -> bool:
    return all(
        [
            getattr(request.app.state, "mcp_connected", False),
            getattr(request.app.state, "db_available", False),
            getattr(request.app.state, "vector_available", False),
        ]
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Liveness check — returns 200 when the process is running."""
    return _build_health_response(request)


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse | JSONResponse:
    """Readiness check — returns 503 when critical dependencies are unavailable."""
    response = _build_health_response(request)
    if not _is_ready(request):
        return JSONResponse(status_code=503, content=response.model_dump())
    return response
