class MCPConnectionError(Exception):
    """Raised when the MCP server cannot be reached or the session fails to start."""

    def __init__(self, message: str = "Failed to connect to the AWS Documentation MCP Server"):
        super().__init__(message)


class MCPToolError(Exception):
    """Raised when an MCP tool call returns an error or unexpected result."""

    def __init__(self, tool: str, detail: str):
        super().__init__(f"MCP tool '{tool}' failed: {detail}")
        self.tool = tool
        self.detail = detail
