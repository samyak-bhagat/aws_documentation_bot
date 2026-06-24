"""MCP client — manages the lifecycle of a stdio connection to the AWS Docs MCP Server."""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core.config import settings
from core.logging import get_logger
from services.mcp.exceptions import MCPConnectionError

logger = get_logger(__name__)


class MCPClient:
    """Async context manager that owns a single MCP stdio session."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: Any = None

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Start the MCP server subprocess and initialise the session."""
        server_params = StdioServerParameters(
            command=settings.mcp_server_command_resolved,
            args=settings.mcp_server_args_list,
            env=None,
        )
        try:
            from contextlib import AsyncExitStack

            self._exit_stack = AsyncExitStack()
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            logger.info("MCP session initialised")
        except Exception as exc:
            raise MCPConnectionError(str(exc)) from exc

    async def disconnect(self) -> None:
        """Gracefully shut down the MCP session."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            logger.info("MCP session closed")

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise MCPConnectionError("MCP session is not open. Use 'async with MCPClient()'.")
        return self._session

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the raw result content."""
        result = await self.session.call_tool(tool_name, arguments=arguments)
        return result


@asynccontextmanager
async def get_mcp_client() -> AsyncGenerator[MCPClient, None]:
    """Convenience async context manager that yields a connected MCPClient."""
    client = MCPClient()
    async with client:
        yield client
