# AWS Documentation Assistant

[![CI](https://github.com/YOUR_USERNAME/aws_documentation_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/aws_documentation_bot/actions/workflows/ci.yml)

An agentic RAG chatbot that answers questions about AWS services using **only official AWS documentation**, with citations back to the source.

> **Core invariant:** Every answer is grounded in retrieved documentation. The agent never generates answers from parametric memory alone.

---

## Architecture

```
User Query
    │
    ▼
FastAPI  ──►  LangGraph Agent
                │
                ├── Query Analyzer   (GPT: extract service + intent)
                ├── Doc Searcher     (MCP: search_documentation)
                ├── Doc Reader       (MCP: read_documentation + in-memory cache)
                ├── Context Builder  (merge + deduplicate)
                ├── Context Evaluator → retry loop (up to 2x)
                ├── Answer Generator (GPT: context-only prompt)
                └── Citation Formatter
                        │
                        ▼
                AWS Docs MCP Server → docs.aws.amazon.com
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- `uv` / `uvx` (installed automatically via pip below)
- OpenAI API key

### Setup

```bash
# 1. Create virtual environment
py -3.11 -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt
pip install uv  # provides uvx for the MCP server

# 3. Configure environment
copy .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Run the API server

```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ask a question

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I secure an S3 bucket?"}'
```

### Run from CLI (no server)

```bash
python -m agents.graph.builder "What are the Lambda function timeout limits?"
```

---

## Development

### Run tests

```bash
# Unit tests (no MCP / LLM required)
pytest tests/unit/ -v

# Phase 1 MCP smoke test
python test_mcp.py
```

### Lint & format

```bash
ruff check .
ruff format .
```

---

## Project Structure

```
aws_documentation_bot/
├── apps/api/           # FastAPI layer (Phase 3)
├── agents/             # LangGraph research agent (Phase 2)
│   ├── graph/          # State + graph builder
│   ├── nodes/          # 7 agent nodes
│   └── prompts/        # Prompt templates
├── services/mcp/       # AWS Docs MCP client (Phase 1)
├── core/               # Config + logging
├── tests/unit/         # 40 unit tests
├── infra/docker/       # Dockerfile (Phase 4)
└── .github/workflows/  # CI pipeline (Phase 4)
```

---

## API Reference

### `POST /chat`

**Request:**
```json
{ "query": "How do I secure an S3 bucket?", "session_id": null }
```

**Response:**
```json
{
  "answer": "To secure an S3 bucket...",
  "sources": [
    { "title": "S3 Security Best Practices", "url": "https://docs.aws.amazon.com/..." }
  ],
  "session_id": "uuid",
  "latency_ms": 4250.0
}
```

### `GET /health`

```json
{ "status": "ok", "mcp_connected": true }
```

---

## Development Phases

| Phase | Status | What |
|---|---|---|
| 1 | ✅ Done | MCP client + tool wrappers |
| 2 | ✅ Done | LangGraph research agent |
| 3 | ✅ Done | FastAPI REST layer |
| 4 | ✅ Done | CI/CD + Docker |
| 5 | Pending | PostgreSQL doc cache |
| 6 | Pending | Daily knowledge sync |
| 7 | Pending | Qdrant vector search |
| 8 | Pending | Auth, observability, Streamlit UI |

---

## GitHub Secret Required

Add `OPENAI_API_KEY` under **GitHub → Settings → Secrets and variables → Actions**.
