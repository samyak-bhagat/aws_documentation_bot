"""
Phase 1 Deliverable — MCP Foundation smoke test.

Usage:
    python test_mcp.py

What it does:
  1. Connects to the AWS Documentation MCP Server
  2. Lists available tools
  3. Searches for "S3 bucket security"
  4. Reads the top result
  5. Prints the content

Done when: real AWS documentation content is printed.
"""

import asyncio
import sys

from services.mcp.client import get_mcp_client
from services.mcp.tools import AWSDocsMCPTools


async def main() -> None:
    print("=" * 60)
    print("AWS Documentation Bot — Phase 1 MCP Test")
    print("=" * 60)

    async with get_mcp_client() as client:
        tools = AWSDocsMCPTools(client)

        # ── List available MCP tools ───────────────────────────────
        print("\n[1] Available MCP tools:")
        tool_list = await client.session.list_tools()
        for tool in tool_list.tools:
            print(f"  • {tool.name}: {tool.description or ''}")

        # ── Search ─────────────────────────────────────────────────
        query = "S3 bucket security"
        print(f"\n[2] Searching for: '{query}'")
        results = await tools.search_documentation(query, limit=5)

        if not results:
            print("  No results returned.")
            sys.exit(1)

        print(f"  Found {len(results)} result(s):")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r.title}")
            print(f"     {r.url}")
            if r.excerpt:
                print(f"     {r.excerpt[:120]}...")

        # ── Read top result ────────────────────────────────────────
        top = results[0]
        if not top.url:
            print("\n  Top result has no URL — skipping read step.")
            sys.exit(1)

        print(f"\n[3] Reading top result: {top.url}")
        doc = await tools.read_documentation(top.url)

        print(f"\n  Title   : {doc.title}")
        print(f"  Sections: {doc.sections[:5]}")
        print("\n  Content preview (first 800 chars):\n")
        print(doc.content[:800])
        print("\n" + "=" * 60)
        print("Phase 1 PASSED — MCP tools are returning real AWS docs.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
