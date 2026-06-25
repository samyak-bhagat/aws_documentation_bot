# AWS Documentation Assistant

[![CI](https://github.com/samyak-bhagat/aws_documentation_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/samyak-bhagat/aws_documentation_bot/actions/workflows/ci.yml)
[![Deploy](https://github.com/samyak-bhagat/aws_documentation_bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/samyak-bhagat/aws_documentation_bot/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)

An agentic RAG chatbot that answers questions about AWS services using **only official AWS documentation**, with citations back to the source.

> **Core invariant:** Every answer is grounded in retrieved documentation. The agent never generates answers from parametric memory alone.

---

## Project Overview

### What it does

The AWS Documentation Assistant accepts natural-language questions about AWS services, retrieves relevant content from [docs.aws.amazon.com](https://docs.aws.amazon.com) via the [AWS Documentation MCP Server](https://awslabs.github.io/mcp/servers/aws-documentation-mcp-server), and synthesizes grounded answers with source citations.

### Problem it solves

AWS documentation is vast and constantly updated. Developers need accurate, cited answers without manually searching dozens of pages. This project automates that research loop with a LangGraph agent that searches, reads, evaluates context quality, and generates answers constrained to retrieved content.

### Key features

| Feature | Implementation |
|---------|----------------|
| Grounded answers with citations | LangGraph agent + context-only answer prompt |
| Live AWS docs access | MCP `search_documentation` / `read_documentation` tools |
| Hybrid retrieval | Amazon OpenSearch (k-NN + BM25 + RRF fusion) |
| Document cache | PostgreSQL `doc_cache` with SHA-256 change detection |
| Multi-turn chat | PostgreSQL chat memory keyed by `session_id` |
| Knowledge sync | Daily APScheduler job driven by AWS What's New RSS |
| Authentication | JWT (register / login / refresh) with bcrypt passwords |
| Rate limiting | `slowapi` per-IP limits on `/chat` |
| Web UI | Streamlit chat interface with login and citation display |
| Production deployment | Docker + Terraform (ECS Fargate, RDS, OpenSearch, Bedrock) |

### High-level architecture

```
User → Streamlit UI / REST API
         │
         ▼
    FastAPI (auth, rate limit, lifespan)
         │
         ├── LangGraph Agent (7 nodes + retry loop)
         │     ├── Query Analyzer      (LLM)
         │     ├── Doc Searcher        (hybrid search OR MCP)
         │     ├── Doc Reader          (PG cache → MCP)
         │     ├── Context Builder
         │     ├── Context Evaluator   → retry up to 2×
         │     ├── Answer Generator    (LLM, context-only)
         │     └── Citation Formatter
         │
         ├── PostgreSQL  (doc cache, chat memory, users)
         ├── Amazon OpenSearch  (vector index)
         └── AWS Docs MCP Server → docs.aws.amazon.com
```

---

## Architecture Snapshot

```mermaid
flowchart TB
    subgraph clients [Clients]
        UI[Streamlit UI :8501]
        CLI[CLI / curl]
    end

    subgraph api [FastAPI :8000]
        Auth[JWT Auth]
        Chat["POST /chat"]
        Admin["POST /admin/*"]
        Health["GET /health"]
    end

    subgraph agent [LangGraph Agent]
        QA[Query Analyzer]
        DS[Doc Searcher]
        DR[Doc Reader]
        CB[Context Builder]
        CE[Context Evaluator]
        AG[Answer Generator]
        CF[Citation Formatter]
        QA --> DS --> DR --> CB --> CE
        CE -->|sufficient| AG
        CE -->|retry| DS
        AG --> CF
    end

    subgraph data [Data Layer]
        PG[(PostgreSQL)]
        VS[(OpenSearch)]
    end

    MCP[AWS Docs MCP Server]

    UI --> Auth
    CLI --> Chat
    Auth --> Chat
    Chat --> agent
    Admin --> PG
    Admin --> VS
    DS --> VS
    DS --> MCP
    DR --> PG
    DR --> MCP
    Chat --> PG
```

Detailed documentation lives in the `docs/` directory:

| Document | Path | Contents |
|----------|------|----------|
| System Architecture | [`docs/system-architecture.md`](docs/system-architecture.md) | Component diagram, data flows, service boundaries |
| API Documentation | [`docs/api.md`](docs/api.md) | Full endpoint reference, request/response schemas, auth |
| AI / RAG Strategy | [`docs/ai-rag-strategy.md`](docs/ai-rag-strategy.md) | Agent graph, retrieval pipeline, prompt strategy |
| Deployment Strategy | [`docs/deployment-strategy.md`](docs/deployment-strategy.md) | Docker Compose, Terraform, ECS, CI/CD |
| Post-Deploy Runbook | [`docs/post-deploy-runbook.md`](docs/post-deploy-runbook.md) | Phase 9 checklist: Terraform, Bedrock, secrets, verification |

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12 |
| **Backend** | FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2 (async), asyncpg |
| **AI / LLM** | LangGraph, LangChain, Amazon Bedrock Claude |
| **Embeddings** | Amazon Titan Embed Text v2 |
| **Knowledge source** | AWS Documentation MCP Server (`awslabs.aws-documentation-mcp-server`) |
| **Vector database** | Amazon OpenSearch Service |
| **Keyword search** | rank-bm25 (hybrid retrieval) |
| **Database** | PostgreSQL 16 (doc cache, chat memory, users) |
| **Scheduling** | APScheduler (daily knowledge sync at 02:00 UTC) |
| **Authentication** | python-jose (JWT HS256), passlib + bcrypt |
| **Rate limiting** | slowapi |
| **UI** | Streamlit |
| **Cloud services** | AWS ECS Fargate, ECR, RDS, OpenSearch, ALB, VPC, Secrets Manager, Route 53, Bedrock |
| **DevOps** | GitHub Actions (CI + deploy), Docker, Docker Compose |
| **Infrastructure** | Terraform ≥ 1.6 (see [`infra/terraform/README.md`](infra/terraform/README.md)) |
| **Testing** | pytest, pytest-asyncio, pytest-cov |
| **Observability** | OpenTelemetry (FastAPI instrumentation) |

---

## Project Structure

```
aws_documentation_bot/
├── apps/
│   ├── api/                    # FastAPI application (v0.9.0)
│   │   ├── main.py             # Lifespan, CORS, rate limiter, router wiring
│   │   ├── schemas.py          # ChatRequest, ChatResponse, HealthResponse
│   │   └── routers/
│   │       ├── chat.py         # POSTING POST /chat — agent invocation
│   │       ├── health.py       # GET /health, /health/ready
│   │       ├── auth.py         # /auth/register, /login, /refresh, /me
│   │       └── admin.py        # POST /admin/sync, /admin/reindex
│   └── ui/
│       └── app.py              # Streamlit chat UI
│
├── agents/
│   ├── graph/
│   │   ├── builder.py          # LangGraph compile + CLI entry point
│   │   └── state.py            # AgentState TypedDict
│   ├── nodes/                  # Seven agent nodes + retry routing
│   └── prompts/                # LLM prompt templates
│
├── services/
│   ├── mcp/                    # AWS Docs MCP client and typed tool wrappers
│   ├── llm/                    # Bedrock LLM factory
│   ├── cache/                  # PostgreSQL document cache (DocCache)
│   ├── memory/                 # Multi-turn chat history
│   ├── vector/                 # OpenSearch client, chunker, indexer, retriever
│   ├── sync/                   # What's New RSS sync pipeline + scheduler
│   └── auth/                   # JWT helpers and User model
│
├── core/
│   ├── config.py               # pydantic-settings (all env vars)
│   ├── database.py             # Async SQLAlchemy + Alembic migrations
│   ├── telemetry.py            # OpenTelemetry tracing
│   └── logging.py              # Structured JSON logger
│
├── alembic/                    # Database migrations
├── tests/unit/                 # 89 unit tests (no live AWS/MCP required)
├── infra/
│   ├── docker/                 # Dockerfile.api, Dockerfile.ui, docker-compose.yml
│   └── terraform/              # AWS infrastructure (VPC, ECS, RDS, OpenSearch, …)
├── scripts/
│   └── check_aws_access.py     # AWS credential sanity check
├── docs/                       # Detailed technical documentation
├── .github/workflows/          # ci.yml (lint, mypy, test, docker build) + deploy.yml
├── .env.example                # Environment variable template
├── requirements.txt
├── pyproject.toml              # Ruff + MyPy + pytest config
├── test_mcp.py                 # Phase 1 MCP smoke test
└── AGENT.md                    # Phase-by-phase development guide
```

---

## Getting Started

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.12 | Matches CI and Docker images |
| `uv` / `uvx` | Launches the AWS Docs MCP Server (`pip install uv`) |
| AWS credentials | Bedrock model access + OpenSearch endpoint (or use ECS) |
| Docker + Docker Compose | Optional — runs API, UI, PostgreSQL (OpenSearch/Bedrock via AWS) |
| PostgreSQL | Required for auth, chat memory, and doc cache via the API |

### Installation

```powershell
# Clone and enter the repo
cd aws_documentation_bot

# Create virtual environment
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# Install dependencies
pip install -r requirements.txt
pip install uv                  # provides uvx for the MCP server

# Configure environment
copy .env.example .env          # Windows
# cp .env.example .env          # Linux / macOS
# Edit .env — set BEDROCK_MODEL_ID, OPENSEARCH_ENDPOINT, DATABASE_URL, AWS credentials
```

Set `APP_ENV=development` for local runs without full AWS stack (API starts with warnings for missing services).

### Environment variables

Copy [`.env.example`](.env.example) to `.env`. See [Configuration](#configuration) for the full reference.

### Local development setup

**Minimal (agent CLI — requires AWS credentials for Bedrock):**

```powershell
$env:APP_ENV = "development"
python -m agents.graph.builder "What are Lambda timeout limits?"
```

**Docker Compose (API + UI + PostgreSQL; set Bedrock/OpenSearch in `.env`):**

```powershell
cd infra/docker
docker compose up --build
```

This starts:

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| Streamlit UI | http://localhost:8501 |
| PostgreSQL | localhost:5432 |

Register a user via the UI or `POST /auth/register`, then chat through the UI or API.

**API only (manual PostgreSQL):**

```powershell
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Streamlit UI (API must be running):**

```powershell
$env:API_URL = "http://localhost:8000"
streamlit run apps/ui/app.py
```

### Running the application

```powershell
# Readiness check (503 if dependencies down)
curl http://localhost:8000/health/ready

# Register (requires DATABASE_URL)
curl -X POST http://localhost:8000/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email": "dev@example.com", "password": "secret123"}'

# Login
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email": "dev@example.com", "password": "secret123"}'

# Chat (Bearer token required)
curl -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <access_token>" `
  -d '{"query": "How do I secure an S3 bucket?"}'
```

### Running tests

```powershell
# Unit tests (89 tests — no live AWS/MCP required)
pytest tests/unit/ -v

# With coverage (matches CI)
pytest tests/unit/ -v --cov=. --cov-report=term-missing

# MCP smoke test (requires live MCP server + network)
python test_mcp.py
```

### Linting

```powershell
ruff check .
mypy services/ agents/ apps/ core/ --ignore-missing-imports
```

### Formatting

```powershell
ruff format .
ruff format --check .    # CI mode — verify without writing
```

### Docker

```powershell
# Build API image
docker build -f infra/docker/Dockerfile.api -t aws-docs-api .

# Build UI image
docker build -f infra/docker/Dockerfile.ui -t aws-docs-ui .

# Full local stack
cd infra/docker
docker compose up --build
```

---

## Configuration

All settings are loaded from environment variables via `core/config.py` (pydantic-settings). Values in `.env` override defaults.

### Required in production (`APP_ENV=production`)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `production` | Strict startup validation |
| `BEDROCK_MODEL_ID` | *(required)* | Bedrock chat model for agent nodes |
| `BEDROCK_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Bedrock embedding model |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock and OpenSearch |
| `OPENSEARCH_ENDPOINT` | *(required)* | OpenSearch domain HTTPS URL |
| `DATABASE_URL` | *(required)* | PostgreSQL async URL |
| `JWT_SECRET` | — | Must not be default in production |
| `MCP_SERVER_COMMAND` | `uvx` | Executable to launch the MCP server |
| `MCP_SERVER_ARGS` | `awslabs.aws-documentation-mcp-server@latest` | MCP server package |

### Optional / tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `production` | Set to `development` for relaxed local startup |
| `OPENSEARCH_INDEX` | `aws_docs` | OpenSearch index name |
| `OPENSEARCH_USERNAME` | *(empty)* | Basic auth user (if not using IAM) |
| `OPENSEARCH_PASSWORD` | *(empty)* | Basic auth password |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `DOC_CACHE_TTL_HOURS` | `24` | Doc cache TTL |
| `MAX_CONTEXT_MESSAGES` | `10` | Multi-turn history window |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-IP rate limit on `/chat` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(empty)* | OTLP trace exporter URL |

### Configuration files

| File | Purpose |
|------|---------|
| `.env` | Local secrets and overrides (never commit) |
| `.env.example` | Documented template for all variables |
| `pyproject.toml` | Ruff, MyPy, and pytest settings |
| `infra/docker/docker-compose.yml` | Local multi-service stack |
| `infra/terraform/environments/dev/terraform.tfvars` | AWS infrastructure variables |

### Secrets required

| Secret | Where |
|--------|-------|
| `JWT_SECRET` | `.env` / Secrets Manager |
| `DATABASE_URL` | `.env` / Secrets Manager (includes DB password) |
| `AWS_ROLE_ARN` | GitHub Actions secret (OIDC deploy role) |

Never commit `.env`, `*accessKeys*.csv`, or `terraform.tfvars` — all are in `.gitignore`.

---

## API Overview

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness check |
| `GET` | `/health/ready` | None | Readiness check (503 if dependencies down) |
| `POST` | `/auth/register` | None | Create user account (requires PostgreSQL) |
| `POST` | `/auth/login` | None | Returns access + refresh JWT pair |
| `POST` | `/auth/refresh` | None | Exchange refresh token for new pair |
| `GET` | `/me` | Bearer | Current user profile |
| `POST` | `/chat` | Bearer | Run research agent; returns answer + citations |
| `POST` | `/admin/sync` | Admin | Trigger knowledge sync pipeline |
| `POST` | `/admin/reindex` | Admin | Re-index cached docs into vector store |

**`POST /chat` response shape:**

```json
{
  "answer": "To secure an S3 bucket...",
  "sources": [{ "title": "S3 Security Best Practices", "url": "https://docs.aws.amazon.com/..." }],
  "session_id": "uuid",
  "latency_ms": 4250.0
}
```

Full endpoint documentation, error codes, and auth flows: [`docs/api.md`](docs/api.md)

Interactive API docs (when server is running): http://localhost:8000/docs

---

## AI / RAG Overview

The research agent is a compiled LangGraph `StateGraph` with seven nodes and a conditional retry loop:

1. **Query Analyzer** — LLM extracts AWS service and intent; produces an optimized search query.
2. **Doc Searcher** — Hybrid vector + BM25 search when the index is populated; otherwise MCP keyword search.
3. **Doc Reader** — Fetches full page content from PostgreSQL cache or MCP (top 3 results).
4. **Context Builder** — Merges and deduplicates document sections.
5. **Context Evaluator** — Checks sufficiency; triggers up to 2 query-broadening retries.
6. **Answer Generator** — LLM synthesizes an answer using **only** the retrieved context.
7. **Citation Formatter** — Attaches source titles and URLs.

LLM and embeddings use Amazon Bedrock exclusively. Vector search uses Amazon OpenSearch.

Detailed retrieval strategy, chunking, indexing, and prompt design: [`docs/ai-rag-strategy.md`](docs/ai-rag-strategy.md)

---

## Deployment

| Environment | Method | Documentation |
|-------------|--------|---------------|
| Local | Docker Compose (`infra/docker/docker-compose.yml`) | [Getting Started](#getting-started) |
| AWS (dev) | Terraform + ECS Fargate | [`infra/terraform/README.md`](infra/terraform/README.md) |
| CI/CD | GitHub Actions on push to `main` | [`docs/deployment-strategy.md`](docs/deployment-strategy.md) |

**CI pipeline** (`.github/workflows/ci.yml`): Ruff lint → Ruff format check → MyPy → pytest with coverage → Docker build.

**Deploy pipeline** (`.github/workflows/deploy.yml`): lint + test → build and push API/UI images to ECR → force ECS rolling deployment. Requires GitHub secret `AWS_ROLE_ARN` (Terraform OIDC output).

Production stack: ECS Fargate (API + Streamlit UI) behind an ALB, RDS PostgreSQL 16, Amazon OpenSearch, ECR, Secrets Manager, and Bedrock for LLM/embeddings.

---

## Development Workflow

### Creating feature branches

```powershell
git checkout main
git pull
git checkout -b feature/your-feature-name
```

### Before opening a pull request

```powershell
ruff check .
ruff format .
mypy services/ agents/ apps/ core/ --ignore-missing-imports
pytest tests/unit/ -v
```

### Pull request process

1. Open a PR targeting `main`.
2. CI must pass: lint, format check, MyPy, unit tests, and Docker build.
3. Keep changes focused; match existing code style and module layout.
4. Do not commit secrets (`.env`, access key CSVs, `terraform.tfvars`).

### CI/CD overview

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | Push / PR to `main` | lint → type-check → test → docker-build |
| `deploy.yml` | Push to `main` / manual dispatch | test → build-and-push (ECR) → deploy (ECS) |

GitHub secret required for deploy: `AWS_ROLE_ARN`. CI unit tests use `APP_ENV=development` (no AWS secrets needed).

---

## Documentation

```
docs/
├── post-deploy-runbook.md   # Phase 9 checklist: Terraform, Bedrock, GitHub secrets, verification
├── system-architecture.md   # Components, data flows, caching, and service boundaries
├── api.md                   # Full REST API reference with auth and admin endpoints
├── ai-rag-strategy.md       # LangGraph agent, hybrid retrieval, prompts, and indexing
└── deployment-strategy.md   # Docker Compose, Terraform, ECS, secrets, and CI/CD
```

| Document | Description |
|----------|-------------|
| [`docs/post-deploy-runbook.md`](docs/post-deploy-runbook.md) | Step-by-step AWS deploy after Phase 9 — Terraform apply, Bedrock, remove `OPENAI_API_KEY`, health checks |
| [`docs/system-architecture.md`](docs/system-architecture.md) | End-to-end system design — API layer, agent, data stores, and MCP integration |
| [`docs/api.md`](docs/api.md) | Complete API contracts, authentication flows, rate limits, and error handling |
| [`docs/ai-rag-strategy.md`](docs/ai-rag-strategy.md) | Agent graph topology, retrieval pipeline (vector + BM25 + RRF), and LLM provider switching |
| [`docs/deployment-strategy.md`](docs/deployment-strategy.md) | Local Docker setup, AWS Terraform provisioning, and GitHub Actions deployment |
| [`infra/terraform/README.md`](infra/terraform/README.md) | Terraform bootstrap, apply, and Bedrock prerequisites |
| [`infra/terraform/README.md`](infra/terraform/README.md) | Step-by-step AWS infrastructure bootstrap and cost estimates |
| [`AGENT.md`](AGENT.md) | Phase-by-phase development history and implementation checklist |

---

## Post-Deploy Checklist (AWS)

After merging Phase 9, complete [`docs/post-deploy-runbook.md`](docs/post-deploy-runbook.md):

1. **`terraform apply`** — applies `APP_ENV=production`, ALB `/health/ready`, ECS health check
2. **Enable Bedrock models** in AWS Console (Claude + Titan Embed v2)
3. **`python scripts/check_aws_access.py`** — confirm Bedrock invoke works
4. **Deploy images** to ECR and force ECS rolling update
5. **Delete `OPENAI_API_KEY`** from GitHub → Settings → Secrets → Actions (obsolete)
6. **`curl http://<alb>/health/ready`** — must return 200 with all dependencies true
7. **Register user**, run `POST /admin/sync` and `POST /admin/reindex`

### Next steps (recommended)

| Priority | Task |
|----------|------|
| High | Enable HTTPS on ALB (`enable_https` + ACM certificate) |
| High | Promote first user to admin; run sync + reindex to populate OpenSearch |
| Medium | Nightly AWS integration smoke tests via GitHub Actions |
| Medium | Set `OTEL_EXPORTER_OTLP_ENDPOINT` for distributed tracing |
| Low | Custom domain (Route 53) and WAF on ALB |

---

## Future Improvements

| Area | Recommendation |
|------|----------------|
| **HTTPS** | Enable ACM certificate on ALB in Terraform |
| **Integration tests** | Nightly GitHub Actions workflow with AWS OIDC |
| **Observability** | ADOT sidecar or OTLP exporter to CloudWatch |
| **Admin bootstrap** | Migration or init script for first admin user |
| **License** | Add root `LICENSE` file |

---

## License

No license file is present in the repository yet. Add one before public distribution.
