from typing import TypedDict


class AgentState(TypedDict, total=False):
    # ── Input ─────────────────────────────────────────────────────────
    user_query: str
    session_id: str

    # ── Query analysis ────────────────────────────────────────────────
    aws_service: str  # e.g. "s3", "ec2", "lambda"
    user_intent: str  # e.g. "security", "pricing", "setup"
    optimized_query: str  # rewritten for better MCP search

    # ── Retrieval ─────────────────────────────────────────────────────
    search_results: list  # list[dict] — serialised SearchResult
    documents: list  # list[dict] — serialised DocumentContent
    context: str  # merged, deduplicated context string

    # ── Generation ───────────────────────────────────────────────────
    answer: str
    citations: list  # list[dict] — {title, url}

    # ── Control ──────────────────────────────────────────────────────
    retry_count: int
    context_sufficient: bool
