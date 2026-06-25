"""Typed wrappers for each AWS Documentation MCP Server tool."""

import json
from typing import Any

from core.logging import get_logger
from services.mcp.client import MCPClient
from services.mcp.exceptions import MCPToolError
from services.mcp.schemas import DocumentContent, SearchResult

logger = get_logger(__name__)

_TOOL_SEARCH = "search_documentation"
_TOOL_READ = "read_documentation"


def _extract_text(content: Any) -> str:
    """Pull plain text out of an MCP tool result's content list."""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "\n".join(parts)
    if hasattr(content, "text"):
        return content.text
    return str(content)


def _parse_json_or_text(raw: str) -> Any:
    """Attempt JSON parse; fall back to the raw string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


class AWSDocsMCPTools:
    """Typed wrappers around the AWS Documentation MCP Server tools."""

    def __init__(self, client: MCPClient) -> None:
        self._client = client

    async def search_documentation(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search AWS documentation. Returns a ranked list of pages."""
        logger.info("Searching AWS docs", extra={"query": query, "limit": limit})
        try:
            result = await self._client.call_tool(
                _TOOL_SEARCH,
                {
                    "search_phrase": query,
                    "search_intent": query,
                    "limit": limit,
                },
            )
        except Exception as exc:
            raise MCPToolError(_TOOL_SEARCH, str(exc)) from exc

        raw_text = _extract_text(result.content)
        parsed = _parse_json_or_text(raw_text)

        if isinstance(parsed, dict) and "search_results" in parsed:
            return [self._sr_from_dict(item) for item in parsed["search_results"]]

        if isinstance(parsed, list):
            return [self._sr_from_dict(item) for item in parsed]

        return [SearchResult(title="Search Result", url="", excerpt=raw_text[:500])]

    async def read_documentation(self, url: str, max_length: int = 10000) -> DocumentContent:
        """Fetch and return the full content of a documentation page."""
        logger.info("Reading AWS doc page", extra={"url": url})
        try:
            result = await self._client.call_tool(
                _TOOL_READ,
                {"url": url, "max_length": max_length},
            )
        except Exception as exc:
            raise MCPToolError(_TOOL_READ, str(exc)) from exc

        raw_text = _extract_text(result.content)
        parsed = _parse_json_or_text(raw_text)

        if isinstance(parsed, dict):
            return DocumentContent(
                url=parsed.get("url", url),
                title=parsed.get("title", ""),
                content=parsed.get("content", raw_text),
                sections=parsed.get("sections", []),
            )

        return DocumentContent(url=url, title="", content=raw_text, sections=[])

    @staticmethod
    def _sr_from_dict(item: Any) -> SearchResult:
        """Convert a search-result dict to a SearchResult model."""
        if isinstance(item, dict):
            return SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                excerpt=item.get("context") or item.get("excerpt") or item.get("description"),
            )
        return SearchResult(title=str(item), url="", excerpt=None)
