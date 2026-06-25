"""FastAPI application.

Lifespan:
  - Validates production configuration
  - Opens a single MCP session on startup (shared by all requests)
  - Runs Alembic migrations and connects PostgreSQL
  - Connects Amazon OpenSearch
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
from core.telemetry import init_telemetry, instrument_fastapi
from services.mcp.client import MCPClient
from services.mcp.tools import AWSDocsMCPTools
from services.sync.scheduler import start_scheduler, stop_scheduler
from services.vector.store import close_vector_store, init_vector_store

logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: validate config, connect MCP, DB, OpenSearch. Shutdown: close all cleanly."""
    init_telemetry()
    settings.validate_production_config()

    app.state.db_available = False
    app.state.vector_available = False
    app.state.mcp_connected = False
    app.state.scheduler_running = False

    if settings.database_url:
        if settings.is_production:
            from core.database import init_db

            await init_db()
            app.state.db_available = True
            logger.info("PostgreSQL connected and migrations applied")
        else:
            try:
                from core.database import init_db

                await init_db()
                app.state.db_available = True
                logger.info("PostgreSQL connected and migrations applied")
            except Exception as exc:
                logger.warning(
                    "PostgreSQL unavailable — running without DB cache",
                    extra={"error": str(exc)},
                )
    elif settings.is_production:
        raise RuntimeError("DATABASE_URL is required in production")

    if settings.vector_search_enabled:
        if settings.is_production:
            await init_vector_store()
            app.state.vector_available = True
            logger.info("OpenSearch connected")
        else:
            try:
                await init_vector_store()
                app.state.vector_available = True
                logger.info("OpenSearch connected")
            except Exception as exc:
                logger.warning(
                    "OpenSearch unavailable — running without vector search",
                    extra={"error": str(exc)},
                )
    elif settings.is_production:
        raise RuntimeError("OPENSEARCH_ENDPOINT is required in production")

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

        scheduler = start_scheduler(mcp_tools, db_available=app.state.db_available)
        app.state.scheduler = scheduler
        app.state.scheduler_running = scheduler.running
    except Exception as exc:
        if settings.is_production:
            raise
        logger.error("MCP connection failed", extra={"error": str(exc)})
        app.state.graph = None
        app.state.mcp_tools = None
        app.state.mcp_client = client
        app.state.mcp_connected = False

    yield

    logger.info("Shutting down")
    stop_scheduler()
    app.state.scheduler_running = False
    await client.disconnect()
    app.state.mcp_connected = False

    if app.state.db_available:
        from core.database import close_db

        await close_db()

    if app.state.vector_available:
        await close_vector_store()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AWS Documentation Assistant",
        description="Answers AWS questions using only official AWS documentation via MCP.",
        version="0.9.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    instrument_fastapi(app)

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
