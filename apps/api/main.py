"""FastAPI application — Phase 8.

Lifespan:
  - Opens a single MCP session on startup (shared by all requests)
  - Initialises PostgreSQL tables (if DATABASE_URL is set)
  - Connects Qdrant (if QDRANT_URL is set)
  - Starts daily knowledge sync scheduler
  - Closes all resources cleanly on shutdown
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agents.graph.builder import build_graph
from apps.api.routers import admin, auth, chat, health
from core.config import settings
from core.logging import get_logger
from services.mcp.client import MCPClient
from services.mcp.tools import AWSDocsMCPTools
from services.sync.scheduler import start_scheduler, stop_scheduler
from services.vector.client import close_qdrant, init_qdrant

logger = get_logger(__name__)

# ── Rate limiter (shared across the app) ─────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: connect MCP + init DB + init Qdrant. Shutdown: close all cleanly."""
    # ── Database (optional — skipped if DATABASE_URL is empty) ────────
    app.state.db_available = False
    if settings.database_url:
        try:
            from core.database import init_db

            await init_db()
            app.state.db_available = True
            logger.info("PostgreSQL connected and tables ready")
        except Exception as exc:
            logger.warning(
                "PostgreSQL unavailable — running without DB cache", extra={"error": str(exc)}
            )

    # ── Qdrant (optional) ────────────────────────────────────────────
    app.state.qdrant_available = False
    if settings.qdrant_url:
        try:
            await init_qdrant()
            app.state.qdrant_available = True
            logger.info("Qdrant connected")
        except Exception as exc:
            logger.warning(
                "Qdrant unavailable — running without vector search", extra={"error": str(exc)}
            )

    # ── MCP server ────────────────────────────────────────────────────
    logger.info("Starting up — connecting to MCP server")
    client = MCPClient()
    try:
        await client.connect()
        mcp_tools = AWSDocsMCPTools(client)
        app.state.mcp_tools = mcp_tools
        app.state.mcp_client = client
        app.state.graph = build_graph(mcp_tools)
        app.state.mcp_connected = True
        logger.info("MCP connected — agent ready")

        app.state.scheduler = start_scheduler(mcp_tools, db_available=app.state.db_available)
    except Exception as exc:
        logger.error("MCP connection failed", extra={"error": str(exc)})
        app.state.graph = None
        app.state.mcp_tools = None
        app.state.mcp_client = client
        app.state.mcp_connected = False

    yield  # ── server is running ──────────────────────────────────────

    logger.info("Shutting down")
    stop_scheduler()
    await client.disconnect()
    app.state.mcp_connected = False

    if app.state.db_available:
        from core.database import close_db

        await close_db()

    if app.state.qdrant_available:
        await close_qdrant()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AWS Documentation Assistant",
        description="Answers AWS questions using only official AWS documentation via MCP.",
        version="0.8.0",
        lifespan=lifespan,
    )

    # ── Rate limiting ─────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # ── CORS ──────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501"],  # Streamlit UI
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
