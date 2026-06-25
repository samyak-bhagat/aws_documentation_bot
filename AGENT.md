# AGENT.md — AWS Documentation Assistant

> Agentic RAG chatbot for AWS Documentation.  
> Phases 1–8 are complete. **Phase 9 (AWS-native production hardening) is complete** on branch `refactor/aws-native-production-hardening`.

---

## Table of Contents

1. [Objective](#objective)
2. [What You Have Right Now](#what-you-have-right-now)
3. [Development Phases](#development-phases)
4. [**Phase 9 — AWS-Native Production Hardening (COMPLETE)**](#phase-9--aws-native-production-hardening-complete)
5. [Phase 1 — MCP Foundation](#phase-1--mcp-foundation)
6. [Phase 2 — Research Agent (LangGraph)](#phase-2--research-agent-langgraph)
7. [Phase 3 — FastAPI Layer](#phase-3--fastapi-layer)
8. [Phase 4 — CI/CD + Docker](#phase-4--cicd--docker)
9. [Phase 5 — Documentation Cache (PostgreSQL)](#phase-5--documentation-cache-postgresql)
10. [Phase 6 — Knowledge Sync Pipeline](#phase-6--knowledge-sync-pipeline)
11. [Phase 7 — Vector Search Layer (Qdrant)](#phase-7--vector-search-layer-qdrant)
12. [Phase 8 — Production Hardening](#phase-8--production-hardening)
13. [Final Architecture](#final-architecture)
14. [Repository Structure](#repository-structure)
15. [Environment Variables](#environment-variables)
16. [Docker Services](#docker-services)
17. [API Contracts](#api-contracts)
18. [Technology Stack](#technology-stack)
19. [Definition of Done](#definition-of-done)

---

## Objective

Build an AI assistant that answers questions about AWS services using **only official AWS documentation**, with citations back to the source.

**Core invariant:** Every answer must be grounded in retrieved documentation. The agent must never generate answers from parametric memory alone.

**Knowledge source:** [AWS Documentation MCP Server](https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server) — always returns the latest AWS docs, no ingestion pipeline needed to start.

---

## What You Have Right Now

| Resource | Status |
|---|---|
| Phases 1–8 (MCP → Auth/UI) | ✅ Implemented |
| AWS ECS / RDS / OpenSearch / Bedrock (Terraform) | ✅ Provisioned |
| GitHub Actions CI + Deploy | ✅ Running |
| Dual-path LLM (OpenAI local / Bedrock AWS) | ✅ Removed in Phase 9 |
| Dual-path vector (Qdrant local / OpenSearch AWS) | ✅ Removed in Phase 9 |
| Alembic migrations | ✅ Implemented (`alembic/versions/001_initial_schema.py`) |
| OpenTelemetry foundation | ✅ Implemented (`core/telemetry.py`) |
| Integration / e2e tests | ❌ Not implemented |

**Stack is AWS-native:** Bedrock + OpenSearch + RDS. Use `APP_ENV=development` for local partial runs.

---

## Development Phases

```mermaid
gantt
    title Development Phases
    dateFormat  X
    axisFormat  Phase %s

    section Foundation
    Phase 1 - MCP Client          :p1, 0, 1
    Phase 2 - Research Agent      :p2, 1, 2
    Phase 3 - FastAPI Layer       :p3, 2, 3

    section Infrastructure
    Phase 4 - CI/CD + Docker      :p4, 3, 4
    Phase 5 - Doc Cache (PG)      :p5, 4, 5
    Phase 6 - Knowledge Sync      :p6, 5, 6

    section Production
    Phase 7 - Vector Search       :p7, 6, 7
    Phase 8 - Production          :p8, 7, 8
```

| Phase | What Gets Built | What You Need |
|---|---|---|
| 1 | MCP client + tool wrappers | OpenAI key |
| 2 | LangGraph research agent | Phase 1 |
| 3 | FastAPI chat endpoint | Phase 2 |
| 4 | GitHub Actions CI + Docker build | GitHub account |
| 5 | PostgreSQL doc cache | Docker |
| 6 | Daily knowledge sync job | Phase 5 |
| 7 | Qdrant vector search | Docker |
| 8 | Auth, observability, rate limiting | Phase 7 |

---

## Phase 9 — AWS-Native Production Hardening (COMPLETE)

> **Handoff document for coding agents.** Execute this plan on branch:
>
> ```
> refactor/aws-native-production-hardening
> ```
>
> Create the branch from `main`:
> ```bash
> git checkout main
> git pull
> git checkout -b refactor/aws-native-production-hardening
> ```

### Context

Phases 1–8 built a working system with **dual backend paths**:

| Concern | Local / dev path (remove) | AWS / production path (keep) |
|---------|---------------------------|------------------------------|
| LLM | OpenAI GPT-4o via `langchain-openai` | Amazon Bedrock Claude via `langchain-aws` |
| Embeddings | OpenAI `text-embedding-3-small` (1536-d) | Bedrock Titan Embed Text v2 (1024-d) |
| Vector search | Qdrant | Amazon OpenSearch (k-NN) |

ECS is **already AWS-native** — Terraform injects `BEDROCK_MODEL_ID`, `OPENSEARCH_ENDPOINT`, and does not set `OPENAI_API_KEY` (`infra/terraform/modules/ecs/main.tf`). Phase 9 removes the legacy local paths, fixes known bugs, and hardens for production.

**Detailed docs (update after each step):** `docs/system-architecture.md`, `docs/api.md`, `docs/ai-rag-strategy.md`, `docs/deployment-strategy.md`, `README.md`.

### Goals

1. Single LLM backend: **Bedrock only**
2. Single vector backend: **OpenSearch only**
3. Remove dead code and unused dependencies
4. Fix sync pipeline OpenSearch indexing bug
5. Fail-fast startup when required AWS services are misconfigured
6. Update CI/CD to remove OpenAI secrets (unit tests do not call OpenAI today)
7. Production hardening: migrations, health checks, observability foundation
8. Clean code: no phase comments, no dual-path `if use_bedrock` branching

### Non-Goals (defer to follow-up PRs)

- LocalStack-based offline dev environment
- WAF / Route 53 custom domain (Terraform supports it; not required for this branch)
- Full Grafana dashboards
- Load testing suite

### Recommended PR Strategy

Split into reviewable PRs on the same branch (or stacked PRs):

| PR | Scope | Depends on |
|----|-------|------------|
| **PR-1** | Fix sync indexing + dead code removal (safe, small) | — |
| **PR-2** | Remove OpenAI + Qdrant code paths | PR-1 |
| **PR-3** | Config fail-fast + expanded `/health` | PR-2 |
| **PR-4** | CI/CD cleanup + docs update | PR-2 |
| **PR-5** | Alembic migrations | PR-3 |
| **PR-6** | OpenTelemetry foundation | PR-3 |

---

### Step 1 — Fix Sync → OpenSearch Indexing (DO FIRST)

**Bug:** `services/sync/scheduler.py` checks Qdrant client directly after cache upsert. On AWS (OpenSearch only), indexing is silently skipped until manual `POST /admin/reindex`.

**File:** `services/sync/scheduler.py` (lines ~123–138)

**Change:**
- Remove import of `services.vector.client._client as qdrant_client`
- Replace with: if `settings.vector_search_enabled` (or always, after Step 2), call `index_document()` from `services/vector/indexer`
- `index_document()` already routes to OpenSearch when `use_opensearch` is true

**Done when:** After `/admin/sync` on AWS, new/changed docs appear in OpenSearch without manual reindex.

---

### Step 2 — Remove OpenAI Code Path

**Files to modify:**

| File | Action |
|------|--------|
| `services/llm/factory.py` | Remove OpenAI branch; always return `ChatBedrock`. Require `bedrock_model_id`. |
| `services/vector/embedder.py` | Remove `_get_openai`, `_embed_openai`, `_openai_client`; always use `_embed_bedrock`. |
| `core/config.py` | Remove `openai_api_key`, `openai_model`, `use_bedrock` property (Bedrock is always on). Make `bedrock_model_id` required (non-empty default or validator). |
| `requirements.txt` | Remove `openai`, `langchain-openai` |
| `.env.example` | Remove `OPENAI_API_KEY`, `OPENAI_MODEL` |

**Done when:** `grep -r "openai\|ChatOpenAI\|langchain_openai" --include="*.py" .` returns no matches outside tests/docs/history.

---

### Step 3 — Remove Qdrant Code Path

**Files to DELETE:**

```
services/vector/client.py
```

**Files to MODIFY:**

| File | Action |
|------|--------|
| `services/vector/store.py` | OpenSearch only — remove Qdrant imports and `use_qdrant` branches |
| `services/vector/retriever.py` | Remove `_qdrant_vector_search`, `_qdrant_bm25_search`; keep OpenSearch implementations only |
| `services/vector/indexer.py` | Remove `_upsert_qdrant` and Qdrant branch in `index_document()` |
| `core/config.py` | Remove `qdrant_url`, `qdrant_collection`, `use_qdrant`, `use_opensearch` flags. `OPENSEARCH_ENDPOINT` becomes required. |
| `apps/api/main.py` | Update lifespan comments; vector init is OpenSearch only |
| `agents/nodes/doc_searcher.py` | Update docstring (remove "Qdrant" references) |
| `apps/api/routers/admin.py` | Update docstrings ("Qdrant" → "vector store" / "OpenSearch") |
| `infra/docker/docker-compose.yml` | Remove `qdrant` service, `qdrant_data` volume, `QDRANT_URL` env |
| `requirements.txt` | Remove `qdrant-client[fastembed]` |
| `.env.example` | Remove `QDRANT_URL`, `QDRANT_COLLECTION` |

**Done when:** `grep -r "qdrant\|Qdrant" --include="*.py" .` returns no matches outside docs/AGENT.md history.

---

### Step 4 — Remove Dead Code

| Item | Location | Action |
|------|----------|--------|
| Unused `_get_session()` | `apps/api/routers/auth.py:61` | Delete function |
| Unused MCP tools | `services/mcp/tools.py` | Delete `read_sections()`, `recommend()` and their constants unless tests cover them |
| Stale terraform note | `infra/terraform/README.md:111` | Remove "Application code changes still required" section (Bedrock/OpenSearch migration is done) |
| Phase comment noise | All `*.py` | Remove `# Phase N` comments; keep meaningful docstrings only |

**Alembic:** Listed in `requirements.txt` but unused. **Keep the dependency** — Step 7 adds migrations. Do not remove yet.

---

### Step 5 — Configuration: Fail-Fast Startup

**File:** `core/config.py`

Add a `validate_production_config()` method or Pydantic `@model_validator` that raises on startup if any required var is empty:

| Variable | Required |
|----------|----------|
| `BEDROCK_MODEL_ID` | Yes |
| `BEDROCK_EMBED_MODEL_ID` | Yes (has default) |
| `AWS_REGION` | Yes (has default) |
| `OPENSEARCH_ENDPOINT` | Yes |
| `DATABASE_URL` | Yes (auth + cache + memory require it) |
| `JWT_SECRET` | Yes — reject default `change-me-in-production` in non-dev |

**File:** `apps/api/main.py`

- Call validation at start of `lifespan` before connecting services
- Change PostgreSQL / OpenSearch init from warn-and-continue to **raise** (or gate behind `ENV=development` flag for local mock mode)

**Optional dev escape hatch (recommended):**

```bash
APP_ENV=development   # allows missing OpenSearch with warning (CLI agent only)
APP_ENV=production    # strict — default on ECS
```

**Done when:** API refuses to start without Bedrock + OpenSearch + DB in production mode.

---

### Step 6 — Expanded Health Checks

**File:** `apps/api/routers/health.py`, `apps/api/schemas.py`

Extend `HealthResponse`:

```json
{
  "status": "ok",
  "mcp_connected": true,
  "database_connected": true,
  "vector_store_connected": true,
  "scheduler_running": true
}
```

Populate from `request.app.state` flags set in lifespan.

Add `GET /health/ready` (optional) that returns `503` if any critical dependency is down — use for ECS health checks.

**File:** `infra/terraform/modules/ecs/main.tf` — point ECS health check to `/health/ready` if added.

---

### Step 7 — Alembic Database Migrations

**Create:**

```
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 001_initial_schema.py
```

Initial migration must create tables currently defined in:

- `services/cache/models.py` → `aws_docs_cache`
- `services/memory/models.py` → `chat_sessions`, `chat_messages`
- `services/auth/models.py` → `users`

**File:** `core/database.py`

- Replace `Base.metadata.create_all` with Alembic upgrade on startup **or** run migrations as ECS init container / deploy step
- Prefer: migrations run in CI/deploy, not on every app boot

**Done when:** Fresh RDS instance can be initialised with `alembic upgrade head` without `create_all()`.

---

### Step 8 — CI/CD Updates

**Current state:** Unit tests (`tests/unit/`) do **not** call OpenAI, Bedrock, or Qdrant. `OPENAI_API_KEY` in CI is unnecessary.

#### `.github/workflows/ci.yml`

| Change | Detail |
|--------|--------|
| Remove | `OPENAI_API_KEY`, `OPENAI_MODEL` from `test` job env |
| Replace | `langchain-openai` in mypy install → `langchain-aws` |
| Add (optional) | `workflow_call` reusable test job for deploy to consume |

#### `.github/workflows/deploy.yml`

| Change | Detail |
|--------|--------|
| Remove | `OPENAI_API_KEY` from test job |
| Keep | `AWS_ROLE_ARN` for ECR push + ECS deploy (unchanged) |

#### New (optional): `.github/workflows/integration.yml`

- Trigger: `workflow_dispatch` or nightly cron
- Uses `AWS_ROLE_ARN` OIDC
- Smoke tests: Bedrock invoke, OpenSearch ping, MCP connectivity
- **Not required for every PR** — too slow/costly

#### GitHub Secrets after Phase 9

| Secret | Still needed? |
|--------|---------------|
| `OPENAI_API_KEY` | **Remove** |
| `AWS_ROLE_ARN` | Yes (deploy + optional integration) |

**Done when:** CI passes with zero OpenAI references; deploy workflow unchanged except secret removal.

---

### Step 9 — Local Development Story (Post-Migration)

After removing OpenAI/Qdrant, local dev options:

| Mode | Setup | Use case |
|------|-------|----------|
| **AWS credentials** | `.env` with Bedrock + OpenSearch endpoints (or SSM port-forward to RDS/OpenSearch) | Full integration testing |
| **Docker Compose (slim)** | API + UI + PostgreSQL only; OpenSearch/Bedrock via AWS | Partial local stack |
| **CLI agent** | `python -m agents.graph.builder "..."` with AWS creds | Agent debugging |
| **Mock mode** | `APP_ENV=development` + mock LLM/embedder fixtures | Unit/dev without AWS costs |

Update `infra/docker/docker-compose.yml` to PostgreSQL + API + UI only (no Qdrant).

Document in `README.md` and `docs/deployment-strategy.md`.

---

### Step 10 — Observability Foundation

**Create:** `core/telemetry.py`

- OpenTelemetry tracer provider (stdout exporter for dev; OTLP for ECS)
- Instrument FastAPI (`opentelemetry-instrumentation-fastapi`)
- Span around each LangGraph node invocation
- Span around Bedrock `invoke_model` and OpenSearch queries

**Add to requirements.txt:**

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-fastapi
opentelemetry-exporter-otlp
```

**ECS:** CloudWatch already configured in task definition. OTEL can export to CloudWatch via ADOT sidecar (defer sidecar to follow-up).

**Done when:** A `/chat` request produces trace spans visible in logs or OTLP collector.

---

### Step 11 — Clean Code Standards

Apply across all touched files:

1. **No dual-path branching** — one backend per concern
2. **No `# Phase N` comments** — use module docstrings
3. **Dependency injection** — pass `mcp_tools`, `db_session`, LLM into graph builder (already partial; extend where globals remain)
4. **Consistent error responses** — map internal exceptions to HTTP status codes; never expose raw stack traces in `detail`
5. **Type hints** — maintain mypy clean on `services/ agents/ apps/ core/`
6. **Tests** — update/add unit tests for config validation, health schema, embedder (mock boto3)

Run before every commit:

```bash
ruff check .
ruff format .
mypy services/ agents/ apps/ core/ --ignore-missing-imports
pytest tests/unit/ -v
```

---

### Step 12 — Documentation Updates

After code changes, update:

| File | Changes |
|------|---------|
| `README.md` | Remove OpenAI/Qdrant from tech stack, prerequisites, env vars |
| `docs/system-architecture.md` | Single-backend diagrams; remove Qdrant/OpenAI nodes |
| `docs/ai-rag-strategy.md` | Bedrock-only LLM/embedder; OpenSearch-only retrieval |
| `docs/deployment-strategy.md` | Updated docker-compose; remove OpenAI CI secrets |
| `docs/api.md` | Expanded health response schema |
| `AGENT.md` | Mark Phase 9 complete; update Technology Stack table below |

---

### Files Inventory (Quick Reference)

#### DELETE

```
services/vector/client.py
```

#### MODIFY (core migration)

```
core/config.py
core/database.py
services/llm/factory.py
services/vector/embedder.py
services/vector/store.py
services/vector/retriever.py
services/vector/indexer.py
services/sync/scheduler.py
apps/api/main.py
apps/api/routers/health.py
apps/api/routers/admin.py
apps/api/routers/auth.py
apps/api/schemas.py
agents/nodes/doc_searcher.py
requirements.txt
.env.example
infra/docker/docker-compose.yml
.github/workflows/ci.yml
.github/workflows/deploy.yml
infra/terraform/README.md
README.md
docs/*.md
```

#### CREATE (production hardening)

```
alembic/env.py
alembic/versions/001_initial_schema.py
core/telemetry.py          (Step 10)
.github/workflows/integration.yml   (optional, Step 8)
```

---

### Phase 9 Definition of Done

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | No OpenAI code or dependencies | `grep -r openai --include="*.py"` clean |
| 2 | No Qdrant code or dependencies | `grep -r qdrant --include="*.py"` clean |
| 3 | Sync indexes to OpenSearch automatically | Run `/admin/sync`, query OpenSearch |
| 4 | API fails fast without required env vars | Start without `BEDROCK_MODEL_ID` → exit |
| 5 | `/health` reports all dependency status | curl `/health` |
| 6 | CI passes without `OPENAI_API_KEY` | Green GitHub Actions |
| 7 | ECS deploy succeeds | Push to main, services stable |
| 8 | Alembic migrations work on fresh DB | `alembic upgrade head` on empty RDS |
| 9 | All docs updated | No OpenAI/Qdrant in README or docs/ |
| 10 | Unit tests pass | `pytest tests/unit/ -v` |

---

### Target Architecture (Post Phase 9)

```mermaid
flowchart TB
    User[User] --> ALB[ALB]
    ALB --> UI[Streamlit ECS]
    ALB --> API[FastAPI ECS]
    UI --> API

    API --> Agent[LangGraph Agent]
    Agent --> Bedrock[Amazon Bedrock<br/>Claude + Titan Embed]
    Agent --> OS[Amazon OpenSearch<br/>k-NN + BM25]
    Agent --> MCP[AWS Docs MCP Server]
    Agent --> RDS[(RDS PostgreSQL)]

    MCP --> AWSDocs[docs.aws.amazon.com]
```

**Single stack. No OpenAI. No Qdrant.**

---

## Phase 1 — MCP Foundation

**Goal:** Connect to the AWS Documentation MCP Server and expose its tools as typed Python interfaces.

**You need:** OpenAI key (for Phase 2), Python 3.12, `uv` or `pip`.

### MCP Server Setup

Reference: https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server

Install via `uvx` (preferred — no Docker needed at this phase):

```bash
uvx awslabs.aws-documentation-mcp-server@latest
```

Or via Docker:

```bash
docker run --rm -i public.ecr.aws/awslabs/aws-documentation-mcp-server:latest
```

### Directory Structure

```
services/
└── mcp/
    ├── __init__.py
    ├── client.py       # MCP connection + lifecycle
    ├── tools.py        # Typed wrappers for each MCP tool
    ├── schemas.py      # Pydantic models for inputs/outputs
    └── exceptions.py   # MCPConnectionError, MCPToolError
```

### MCP Tool Wrappers

```python
# services/mcp/schemas.py

from pydantic import BaseModel

class SearchResult(BaseModel):
    title: str
    url: str
    excerpt: str | None = None

class DocumentContent(BaseModel):
    url: str
    title: str
    content: str
    sections: list[str]

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class ReadRequest(BaseModel):
    url: str
```

```python
# services/mcp/tools.py

class AWSDocsMCPClient:
    """Typed client wrapping the AWS Documentation MCP Server tools."""

    async def search_documentation(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search AWS documentation. Returns ranked list of pages."""
        ...

    async def read_documentation(self, url: str) -> DocumentContent:
        """Fetch and return full content of a documentation page."""
        ...

    async def read_sections(self, url: str) -> list[str]:
        """Return section headings of a documentation page."""
        ...

    async def recommend(self, url: str) -> list[SearchResult]:
        """Return related pages recommended by the MCP server."""
        ...
```

### MCP Tool Flow

```mermaid
flowchart LR
    A["Python Agent"] -->|"search_documentation(query)"| MCP["AWS Docs\nMCP Server"]
    MCP -->|"list[SearchResult]"| A
    A -->|"read_documentation(url)"| MCP
    MCP -->|"DocumentContent"| A
    MCP -->|"HTTP"| AWS["docs.aws.amazon.com"]

    style MCP fill:#ff9900,color:#fff
    style AWS fill:#232f3e,color:#fff
```

### Phase 1 Deliverable

A `test_mcp.py` script that:
1. Connects to the MCP server
2. Searches for "S3 bucket security"
3. Reads the top result
4. Prints the content

**Done when:** MCP tools return real AWS documentation content.

---

## Phase 2 — Research Agent (LangGraph)

**Goal:** A LangGraph agent that answers AWS questions using only MCP-retrieved documentation.

**No vector database. No embeddings. MCP is the knowledge source.**

### Agent Workflow

```mermaid
flowchart TD
    START([START]) --> QA["Query Analyzer\nIdentify service + intent\nGenerate optimized search query"]
    QA --> SD["Search Docs\nsearch_documentation()"]
    SD --> RD["Read Docs\nread_documentation() on top results"]
    RD --> CB["Context Builder\nMerge + deduplicate content"]
    CB --> EC{"Context\nSufficient?"}
    EC -->|YES| GA["Generate Answer\nGPT-4.1 — docs context only"]
    EC -->|NO| FB["Broaden Search\nExpand query terms"]
    FB --> RetryCheck{"retry_count < 2?"}
    RetryCheck -->|YES| SD
    RetryCheck -->|NO| GA
    GA --> CF["Citation Formatter\nAttach source URLs + titles"]
    CF --> END([END])

    style START fill:#10b981,color:#fff
    style END fill:#10b981,color:#fff
    style EC fill:#f59e0b,color:#fff
    style RetryCheck fill:#f59e0b,color:#fff
```

### Agent State

```python
# agents/graph/state.py

from typing import TypedDict

class AgentState(TypedDict):
    # Input
    user_query: str
    session_id: str

    # Query analysis
    aws_service: str          # e.g. "s3", "ec2", "lambda"
    user_intent: str          # e.g. "security", "pricing", "setup"
    optimized_query: str      # rewritten for better MCP search

    # Retrieval
    search_results: list      # list[SearchResult]
    documents: list           # list[DocumentContent] — full page content
    context: str              # merged, deduplicated context string

    # Generation
    answer: str
    citations: list           # list[Citation]

    # Control
    retry_count: int
    context_sufficient: bool
```

### Node Implementations

```
agents/
├── graph/
│   ├── __init__.py
│   ├── state.py          # AgentState TypedDict
│   └── builder.py        # Compile LangGraph graph
└── nodes/
    ├── query_analyzer.py     # Identify service, intent, optimized query
    ├── doc_searcher.py       # Call search_documentation()
    ├── doc_reader.py         # Call read_documentation() on top N results
    ├── context_builder.py    # Merge docs, remove duplicates
    ├── context_evaluator.py  # Decide if context is sufficient
    ├── answer_generator.py   # Call OpenAI with context-only prompt
    └── citation_formatter.py # Build citation list from read documents
```

### Query Analyzer Example

```
Input:  "How do I secure an S3 bucket?"

Output:
{
  "aws_service": "s3",
  "user_intent": "security",
  "optimized_query": "Amazon S3 bucket security best practices"
}
```

### Answer Generator Prompt (Hard Rules)

```
System:
You are an AWS documentation assistant.
Answer ONLY using the provided documentation context.
Do NOT use any knowledge outside of the provided context.
If the context does not contain enough information, say:
"I could not find this information in the AWS documentation provided."
Always end your answer with the sources you used.

Context:
{context}

Question:
{user_query}
```

### Citation Schema

```python
class Citation(BaseModel):
    title: str
    url: str
```

### Phase 2 Deliverable

Run agent from CLI:

```bash
python -m agents.graph.builder "How do I secure an S3 bucket?"
```

Output:
```
Answer: ...
Sources:
  - Amazon S3 Security Best Practices → https://docs.aws.amazon.com/...
  - AWS IAM Policies for S3 → https://docs.aws.amazon.com/...
```

**Done when:** Agent returns a grounded, cited answer for any AWS question.

---

## Phase 3 — FastAPI Layer

**Goal:** Expose the Phase 2 agent through a REST API.

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Liveness check |
| POST | `/chat` | No (Phase 3) / Yes (Phase 8) | Ask a question |

### Request / Response Contracts

```python
# apps/api/schemas.py

class ChatRequest(BaseModel):
    query: str                          # required, 1–2000 chars
    session_id: str | None = None       # optional, for multi-turn (Phase 5+)

class Citation(BaseModel):
    title: str
    url: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[Citation]
    session_id: str
    latency_ms: float

class HealthResponse(BaseModel):
    status: str                         # "ok"
    mcp_connected: bool
```

### App Structure

```
apps/
└── api/
    ├── __init__.py
    ├── main.py           # FastAPI app, lifespan, CORS
    ├── routers/
    │   ├── chat.py       # POST /chat
    │   └── health.py     # GET /health
    └── schemas.py        # ChatRequest, ChatResponse, Citation
```

### Phase 3 Deliverable

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I set up a VPC?"}'
```

Returns valid `ChatResponse` JSON.

---

## Phase 4 — CI/CD + Docker

**Goal:** GitHub Actions pipeline that lints, tests, and builds a Docker image locally. No cloud deployment needed yet.

**This is the first thing you can set up in parallel with Phase 1–3.**

### GitHub Actions CI Pipeline

```mermaid
flowchart LR
    PR["Push / PR"] --> LINT["Ruff\n(lint + format check)"]
    LINT --> TYPE["MyPy\n(type check)"]
    TYPE --> TEST["pytest\n(unit tests)"]
    TEST --> BUILD["docker build\n(verify image builds)"]

    style PR fill:#24292e,color:#fff
    style BUILD fill:#10b981,color:#fff
```

### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  type-check:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mypy
      - run: mypy services/ agents/ apps/

  test:
    runs-on: ubuntu-latest
    needs: type-check
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ -v --cov=. --cov-report=term-missing

  docker-build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f infra/docker/Dockerfile.api -t aws-docs-api:ci .
```

### GitHub Secret Required

Add `OPENAI_API_KEY` under **GitHub → Settings → Secrets → Actions**.

### Dockerfile (Phase 4 version — minimal)

```dockerfile
# infra/docker/Dockerfile.api
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Phase 4 Deliverable

- Green CI badge on GitHub README
- `docker build` succeeds locally and in Actions
- `OPENAI_API_KEY` stored as GitHub Secret (not in code)

---

## Phase 5 — Documentation Cache (PostgreSQL)

**Goal:** Cache MCP-fetched pages in PostgreSQL to reduce repeated MCP calls and enable multi-turn memory.

**Introduced via Docker Compose — no cloud needed.**

### `docker-compose.yml` (Phase 5+)

```yaml
services:
  api:
    build:
      context: .
      dockerfile: infra/docker/Dockerfile.api
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: aws_docs
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Database Schema

```mermaid
erDiagram
    aws_docs_cache {
        uuid id PK
        text url UK
        text title
        text content
        text hash
        timestamp last_fetched
        timestamp last_checked
    }
    chat_sessions {
        uuid id PK
        text session_id UK
        timestamp created_at
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        text role
        text content
        jsonb citations
        int tokens_used
        float latency_ms
        timestamp created_at
    }

    chat_sessions ||--o{ chat_messages : "contains"
```

### Cache Lookup Flow

```mermaid
flowchart TD
    RD["Doc Reader Node\nread_documentation(url)"]
    CHK{"URL in\naws_docs_cache?"}
    FRESH{"last_fetched\n< 24h ago?"}
    USE["Use Cached Content"]
    FETCH["Fetch from MCP Server"]
    STORE["Store in Cache\n(url, content, hash, timestamp)"]

    RD --> CHK
    CHK -->|YES| FRESH
    CHK -->|NO| FETCH
    FRESH -->|YES| USE
    FRESH -->|NO| FETCH
    FETCH --> STORE
    STORE --> USE

    style USE fill:#10b981,color:#fff
    style FETCH fill:#f59e0b,color:#fff
```

### Session-Based Multi-Turn

With `session_id` now persisted, `/chat` accepts:

```json
{
  "query": "What encryption options does it support?",
  "session_id": "abc-123"
}
```

The agent loads the last N messages from `chat_messages` and includes them in the LLM prompt for context continuity. Limit: last **10 messages** or **4000 tokens**, whichever is smaller.

---

## Phase 6 — Knowledge Sync Pipeline

**Goal:** Run a daily job that checks AWS What's New, identifies important service updates, fetches updated documentation, and refreshes the cache.

### Sync Workflow

```mermaid
flowchart TD
    SCH["⏰ Daily Scheduler\n(APScheduler)"] --> WN["Fetch AWS What's New\nhttps://aws.amazon.com/new/"]
    WN --> ID["Identify Affected Services\n(LLM extracts service names)"]
    ID --> SD["Search Documentation\nfor each affected service"]
    SD --> FD["Fetch + Read Updated Pages\nvia MCP"]
    FD --> HASH["Compute SHA256 Hash"]
    HASH --> CHK{"Hash Changed?"}
    CHK -->|NO| SKIP["Skip — content unchanged"]
    CHK -->|YES| UPD["Update Cache\n(content + hash + last_fetched)"]
    UPD --> DONE(["✅ Cache Updated"])

    style SCH fill:#7c3aed,color:#fff
    style CHK fill:#f59e0b,color:#fff
    style SKIP fill:#6b7280,color:#fff
    style DONE fill:#10b981,color:#fff
```

### Trigger Options

- **Scheduled:** APScheduler job runs daily at 02:00 UTC
- **Manual:** `POST /admin/sync` endpoint triggers on-demand (no auth required in dev)

### Key Constraint

Never delete cache entries. Always upsert by `url`. If a page is removed from AWS docs, mark it `deprecated: true` but keep the content.

---

## Phase 7 — Vector Search Layer (Qdrant)

**Goal:** Add semantic vector search over the cached documentation to improve retrieval quality.

MCP remains the source of truth. Qdrant is an optimization layer over the PostgreSQL cache.

### Updated `docker-compose.yml` (Phase 7+)

Add Qdrant service:

```yaml
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  qdrant_data:
```

### Qdrant Collection Config

```python
COLLECTION_NAME = "aws_docs"
VECTOR_SIZE = 1536          # text-embedding-3-small dimensions
DISTANCE = Distance.COSINE

# Payload fields indexed for filtering:
# - service_name (keyword)
# - url (keyword)
# - last_updated (datetime)
```

### Chunking Strategy

```mermaid
graph TD
    D["Cached Document\n(PostgreSQL)"] --> S["Section\n(by heading)"]
    S --> C1["Chunk ≤1000 tokens"]
    S --> C2["Chunk ≤1000 tokens"]
    C1 -. "150 token\noverlap" .-> C2
```

Each chunk stored in Qdrant payload:

```json
{
  "url": "https://docs.aws.amazon.com/...",
  "title": "Amazon S3 Security Best Practices",
  "section": "Block Public Access",
  "service_name": "s3",
  "chunk_text": "...",
  "hash": "sha256:abc123"
}
```

### Hybrid Retrieval Flow

```mermaid
flowchart TD
    Q["User Query"]
    CHK{"Qdrant\nHas Docs?"}
    VS["Vector Search\nTop 20 (Qdrant)"]
    BM["BM25 Search\nTop 20 (rank_bm25)"]
    MCP["Query MCP Server\n+ update cache"]
    RRF["Reciprocal Rank Fusion\nMerge results"]
    RR["Cross-Encoder Reranking\nbge-reranker-large"]
    TOP5["Top 5 Chunks → LLM"]

    Q --> CHK
    CHK -->|YES| VS
    CHK -->|YES| BM
    CHK -->|NO| MCP
    MCP --> VS
    VS --> RRF
    BM --> RRF
    RRF --> RR
    RR --> TOP5

    style MCP fill:#ff9900,color:#fff
```

---

## Phase 8 — Production Hardening

**Goal:** Add authentication, observability, rate limiting, and UI.

### Updated `docker-compose.yml` (Phase 8 — full stack)

```yaml
services:
  api:
    build: { context: ., dockerfile: infra/docker/Dockerfile.api }
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, qdrant]

  ui:
    build: { context: ., dockerfile: infra/docker/Dockerfile.ui }
    ports: ["8501:8501"]
    env_file: .env
    depends_on: [api]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: aws_docs
    volumes: [postgres_data:/var/lib/postgresql/data]

  qdrant:
    image: qdrant/qdrant:latest
    volumes: [qdrant_data:/qdrant/storage]

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    volumes: ["./infra/otel/config.yaml:/etc/otel/config.yaml"]

  prometheus:
    image: prom/prometheus:latest
    volumes: ["./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    depends_on: [prometheus]

volumes:
  postgres_data:
  qdrant_data:
```

### JWT Authentication

Added endpoints:

| Method | Path | Auth |
|---|---|---|
| POST | `/auth/register` | No |
| POST | `/auth/login` | No |
| POST | `/auth/refresh` | Refresh token |
| GET | `/me` | Bearer token |
| POST | `/chat` | Bearer token |
| GET | `/history` | Bearer token |
| POST | `/admin/sync` | Bearer token (admin) |

### Observability

```mermaid
flowchart LR
    API["FastAPI"] -->|"spans"| OTEL["OTel Collector"]
    LG["LangGraph"] -->|"spans"| OTEL
    MCP_C["MCP Client"] -->|"spans"| OTEL
    OTEL --> PROM["Prometheus"]
    PROM --> GRAF["Grafana"]
```

Structured log fields per request:

```json
{
  "request_id": "uuid",
  "user_id": "uuid",
  "session_id": "uuid",
  "total_latency_ms": 0,
  "mcp_latency_ms": 0,
  "llm_latency_ms": 0,
  "token_usage": { "prompt": 0, "completion": 0 },
  "pages_read": 0,
  "cache_hit": false,
  "vector_search_used": false
}
```

### Security

| Requirement | Implementation |
|---|---|
| Authentication | JWT HS256, FastAPI Users + python-jose |
| Secrets | `.env` file (never committed), GitHub Secrets for CI |
| Rate limiting | `slowapi` — 20 req/min per user on `/chat` |
| Input validation | Pydantic v2 on all request bodies |
| SQL injection | SQLAlchemy ORM, no raw SQL |
| Prompt injection | Input sanitization before inserting into prompts |
| CORS | Allowlist: `http://localhost:8501` in dev |

---

## Final Architecture

```mermaid
graph TD
    User["👤 User"]
    UI["Streamlit UI\nPort 8501"]
    API["FastAPI\nPort 8000\nJWT Auth"]
    LG["LangGraph Agent\n6 nodes"]

    QAN["Query Analyzer"]
    DS["Doc Searcher"]
    DR["Doc Reader"]
    CB["Context Builder"]
    AG["Answer Generator\nGPT-4.1"]
    CF["Citation Formatter"]

    CACHE{"PostgreSQL Cache\nHit?"}
    MCP["AWS Docs\nMCP Server"]
    AWS["docs.aws.amazon.com"]
    QD[("Qdrant\nVector DB")]
    PG[("PostgreSQL\nCache + Memory")]
    OTEL["OpenTelemetry\n→ Prometheus → Grafana"]

    User --> UI
    UI -->|"REST"| API
    API --> LG

    LG --> QAN --> DS --> DR
    DR --> CACHE
    CACHE -->|HIT| CB
    CACHE -->|MISS| MCP
    MCP --> AWS
    MCP --> PG
    PG --> CB

    DR -.->|"Phase 7+"| QD
    QD --> CB

    CB --> AG --> CF
    CF -->|"answer + citations"| API

    API -.->|"traces"| OTEL
    LG -.->|"traces"| OTEL

    style MCP fill:#ff9900,color:#fff
    style AWS fill:#232f3e,color:#fff
    style QD fill:#e6f7ff,stroke:#0ea5e9
    style PG fill:#e6f7ff,stroke:#0ea5e9
    style LG fill:#f0f4ff,stroke:#4a6cf7
    style OTEL fill:#f5f0ff,stroke:#7c3aed
```

---

## Repository Structure

```
aws-docs-assistant/
│
├── apps/
│   ├── api/
│   │   ├── main.py               # FastAPI app, lifespan, CORS
│   │   ├── routers/
│   │   │   ├── chat.py           # POST /chat
│   │   │   ├── auth.py           # POST /auth/login, /register  (Phase 8)
│   │   │   ├── history.py        # GET /history                 (Phase 5)
│   │   │   └── admin.py          # POST /admin/sync             (Phase 6)
│   │   └── schemas.py            # ChatRequest, ChatResponse, Citation
│   └── ui/
│       └── app.py                # Streamlit chat UI            (Phase 8)
│
├── agents/
│   ├── graph/
│   │   ├── state.py              # AgentState TypedDict
│   │   └── builder.py            # Compile LangGraph graph
│   ├── nodes/
│   │   ├── query_analyzer.py
│   │   ├── doc_searcher.py
│   │   ├── doc_reader.py
│   │   ├── context_builder.py
│   │   ├── context_evaluator.py
│   │   ├── answer_generator.py
│   │   └── citation_formatter.py
│   └── prompts/
│       ├── query_analysis.txt
│       └── answer_generation.txt
│
├── services/
│   ├── mcp/
│   │   ├── client.py             # MCP connection + lifecycle
│   │   ├── tools.py              # AWSDocsMCPClient
│   │   ├── schemas.py            # SearchResult, DocumentContent
│   │   └── exceptions.py
│   ├── cache/                    # Phase 5: PostgreSQL doc cache
│   │   ├── repository.py
│   │   └── models.py
│   ├── vector_store/             # Phase 7: Qdrant
│   │   ├── client.py
│   │   ├── indexer.py
│   │   └── searcher.py
│   ├── sync/                     # Phase 6: Knowledge sync job
│   │   └── scheduler.py
│   ├── auth/                     # Phase 8
│   │   └── jwt.py
│   └── memory/                   # Phase 5: Chat history
│       └── repository.py
│
├── core/
│   ├── config.py                 # pydantic-settings, all env vars
│   ├── logging.py                # Structured JSON logger
│   └── telemetry.py              # OpenTelemetry setup
│
├── tests/
│   ├── unit/
│   │   ├── test_query_analyzer.py
│   │   ├── test_context_builder.py
│   │   ├── test_citation_formatter.py
│   │   └── test_mcp_schemas.py
│   ├── integration/
│   │   ├── test_mcp_client.py    # Requires live MCP server
│   │   ├── test_cache.py         # Requires PostgreSQL
│   │   └── test_vector_store.py  # Requires Qdrant
│   └── e2e/
│       └── test_chat_api.py      # Full query → answer flow
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.ui
│   │   └── docker-compose.yml
│   ├── otel/
│   │   └── config.yaml
│   └── prometheus/
│       └── prometheus.yml
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .env.example                  # Template — copy to .env, never commit .env
├── requirements.txt
├── pyproject.toml                # Ruff + MyPy config
└── README.md
```

---

## Environment Variables

All configuration via environment variables. Copy `.env.example` → `.env`.

```bash
# .env.example

# ── Required from Phase 1 ──────────────────────────────
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o                   # or gpt-4.1

# ── MCP Server (Phase 1) ──────────────────────────────
MCP_SERVER_COMMAND=uvx
MCP_SERVER_ARGS=awslabs.aws-documentation-mcp-server@latest

# ── PostgreSQL (Phase 5) ──────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/aws_docs

# ── Qdrant (Phase 7) ─────────────────────────────────
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=aws_docs

# ── Auth (Phase 8) ────────────────────────────────────
JWT_SECRET=change-me-in-production    # min 32 chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# ── Cache settings ─────────────────────────────────────
DOC_CACHE_TTL_HOURS=24
MAX_CONTEXT_MESSAGES=10               # multi-turn window

# ── Rate limiting (Phase 8) ───────────────────────────
RATE_LIMIT_PER_MINUTE=20
```

---

## API Contracts

### `POST /chat`

**Request:**
```json
{
  "query": "How do I secure an S3 bucket?",
  "session_id": "optional-uuid-for-multi-turn"
}
```

**Response:**
```json
{
  "answer": "To secure an S3 bucket, you should...",
  "sources": [
    {
      "title": "Amazon S3 Security Best Practices",
      "url": "https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html"
    }
  ],
  "session_id": "uuid",
  "latency_ms": 1240.5
}
```

**Fallback (insufficient context):**
```json
{
  "answer": "I could not find this information in the AWS documentation provided.",
  "sources": [],
  "session_id": "uuid",
  "latency_ms": 890.2
}
```

### `GET /health`

```json
{
  "status": "ok",
  "mcp_connected": true
}
```

---

## Technology Stack

| Layer | Technology | Introduced | Phase 9 target |
|---|---|---|---|
| Language | Python 3.12 | Phase 1 | — |
| Agent Framework | LangGraph + LangChain | Phase 2 | — |
| LLM | ~~GPT-4o (OpenAI)~~ → **Amazon Bedrock Claude** | Phase 2 / 9 | Bedrock only |
| Knowledge Source | AWS Docs MCP Server | Phase 1 | — |
| API | FastAPI + uvicorn | Phase 3 | — |
| CI/CD | GitHub Actions | Phase 4 | Remove OpenAI secrets |
| Containers | Docker + Docker Compose | Phase 4 | Slim compose (no Qdrant) |
| Relational DB | PostgreSQL 16 (RDS) | Phase 5 | Alembic migrations |
| Embeddings | ~~OpenAI text-embedding-3-small~~ → **Bedrock Titan v2** | Phase 7 / 9 | Bedrock only |
| Vector DB | ~~Qdrant~~ → **Amazon OpenSearch** | Phase 7 / 9 | OpenSearch only |
| Keyword Search | rank_bm25 (+ OpenSearch match) | Phase 7 | — |
| UI | Streamlit | Phase 8 | — |
| Auth | python-jose + bcrypt | Phase 8 | — |
| Observability | OpenTelemetry (planned) | Phase 9 | Implement in Step 10 |
| Rate Limiting | slowapi | Phase 8 | — |

---

## Definition of Done

| Phase | Deliverable | Done When |
|---|---|---|
| 1 | MCP Client | `test_mcp.py` returns real AWS doc content |
| 2 | Research Agent | CLI agent answers any AWS question with citations |
| 3 | FastAPI | `POST /chat` returns `ChatResponse` JSON |
| 4 | CI/CD | Green GitHub Actions badge; `docker build` passes |
| 5 | Doc Cache | Repeated queries hit PostgreSQL, not MCP |
| 6 | Sync Job | Daily job updates cache for changed AWS docs |
| 7 | Vector Search | OpenSearch returns semantically relevant chunks |
| 8 | Production | Auth, rate limiting, Streamlit UI all working |
| **9** | **AWS-native hardening** | ✅ Complete — see [Phase 9](#phase-9--aws-native-production-hardening-complete) |
