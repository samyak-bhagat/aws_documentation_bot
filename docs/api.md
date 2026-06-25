# API Documentation

REST API served by FastAPI at `apps/api/main.py` (version **0.8.0**).

**Base URL (local):** `http://localhost:8000`

**Interactive docs:** `http://localhost:8000/docs` (Swagger UI) and `/redoc`

---

## Authentication

Most endpoints require a JWT Bearer token. Obtain tokens via `/auth/login` or `/auth/register` + `/auth/login`.

**Header format:**

```http
Authorization: Bearer <access_token>
```

### Token lifecycle

| Token | Lifetime | Claims |
|-------|----------|--------|
| Access | `JWT_EXPIRE_MINUTES` (default 60 min) | `sub`, `email`, `is_admin`, `type: "access"` |
| Refresh | 7 days | `sub`, `type: "refresh"` |

Implementation: `services/auth/jwt.py` — HS256 signed with `JWT_SECRET`.

### Auth requirements by endpoint

| Endpoint | Auth required | Role |
|----------|---------------|------|
| `GET /health` | No | — |
| `POST /auth/register` | No | — |
| `POST /auth/login` | No | — |
| `POST /auth/refresh` | No (refresh token in body) | — |
| `GET /me` | Yes | Any authenticated user |
| `POST /chat` | Yes | Any authenticated user |
| `POST /admin/sync` | Yes | Admin (`is_admin=true`) |
| `POST /admin/reindex` | Yes | Admin |

> **Note:** Auth endpoints require PostgreSQL (`DATABASE_URL`). Without a database, registration and login return `503 Database not available`.

---

## Rate Limiting

Implemented with `slowapi`:

| Scope | Limit |
|-------|-------|
| Global default | 200 requests/minute per IP |
| `POST /chat` | `RATE_LIMIT_PER_MINUTE` per IP (default **20/minute**) |

Exceeded limits return **429 Too Many Requests**.

---

## Endpoints

### `GET /health`

Liveness check. Does not require authentication. Always returns `200` when the process is running.

**Response** `200 OK`:

```json
{
  "status": "ok",
  "mcp_connected": true,
  "database_connected": true,
  "vector_store_connected": true,
  "scheduler_running": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always `"ok"` when the server is running |
| `mcp_connected` | boolean | Whether the MCP server session is active |
| `database_connected` | boolean | Whether PostgreSQL is connected |
| `vector_store_connected` | boolean | Whether OpenSearch is connected |
| `scheduler_running` | boolean | Whether the sync scheduler is running |

---

### `GET /health/ready`

Readiness check for load balancers and ECS. Returns `503` if MCP, PostgreSQL, or OpenSearch is unavailable.

**Response** `200 OK` or `503 Service Unavailable` — same body shape as `/health`.

---

### `POST /auth/register`

Create a new user account.

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `email` | string | Valid email (Pydantic `EmailStr`) |
| `password` | string | Plain text (hashed with bcrypt server-side) |

**Response** `201 Created`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_admin": false
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `400` | Email already registered |
| `503` | Database not available |

---

### `POST /auth/login`

Authenticate and receive token pair.

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

**Response** `200 OK`:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `401` | Invalid email or password |
| `403` | Account disabled (`is_active=false`) |
| `503` | Database not available |

---

### `POST /auth/refresh`

Exchange a refresh token for a new access + refresh pair.

**Request body:**

```json
{
  "refresh_token": "eyJ..."
}
```

**Response** `200 OK`: Same shape as login (`TokenPair`).

**Errors:**

| Status | Condition |
|--------|-----------|
| `401` | Invalid, expired, or wrong token type |
| `503` | Database not available |

---

### `GET /me`

Return the authenticated user's profile.

**Response** `200 OK`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_admin": false
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `401` | Missing or invalid access token |

---

### `POST /chat`

Run the LangGraph research agent and return a grounded answer with citations.

**Authentication:** Required (Bearer access token).

**Request body:**

```json
{
  "query": "How do I secure an S3 bucket?",
  "session_id": "optional-uuid-for-multi-turn"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `query` | string | Required, 1–2000 characters |
| `session_id` | string \| null | Optional. Omit or pass `null` to start a new session. Reuse to continue a conversation. |

**Multi-turn behaviour:** When `DATABASE_URL` is configured and a `session_id` is provided, the handler loads the last `MAX_CONTEXT_MESSAGES` (default 10) messages from PostgreSQL and prepends them to the query before invoking the agent.

**Response** `200 OK`:

```json
{
  "answer": "To secure an S3 bucket, you should enable block public access...",
  "sources": [
    {
      "title": "Blocking public access to your Amazon S3 storage",
      "url": "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html"
    }
  ],
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "latency_ms": 4250.0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | LLM-generated answer grounded in retrieved docs |
| `sources` | array | Deduplicated citations from documents read |
| `session_id` | string | Session UUID (generated if not provided) |
| `latency_ms` | float | End-to-end agent execution time in milliseconds |

**Fallback answer** (insufficient context after retries):

```json
{
  "answer": "I could not find this information in the AWS documentation provided.",
  "sources": [],
  "session_id": "...",
  "latency_ms": 890.2
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `401` | Missing or invalid access token |
| `429` | Rate limit exceeded |
| `500` | Agent execution error |
| `503` | MCP not connected — agent not initialised |

Schema: `ChatRequest`, `ChatResponse`, `Citation` in `apps/api/schemas.py`

Implementation: `apps/api/routers/chat.py`

---

### `POST /admin/sync`

Manually trigger the knowledge sync pipeline.

**Authentication:** Admin JWT required.

**Request body:** None.

**Response** `200 OK`:

```json
{
  "status": "ok",
  "services_checked": 5,
  "pages_checked": 15,
  "pages_updated": 3,
  "pages_skipped": 12,
  "errors": 0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `services_checked` | int | Services identified from What's New RSS |
| `pages_checked` | int | Documentation pages read via MCP |
| `pages_updated` | int | Pages written to cache (content changed) |
| `pages_skipped` | int | Pages unchanged or DB unavailable |
| `errors` | int | Failed RSS fetch, search, or read operations |

**Errors:**

| Status | Condition |
|--------|-----------|
| `403` | Non-admin user |
| `503` | MCP not connected |

Implementation: `services/sync/scheduler.py` → `run_sync()`

---

### `POST /admin/reindex`

Re-index all non-deprecated documents from PostgreSQL into the vector store.

**Authentication:** Admin JWT required.

**Request body:** None.

**Response** `200 OK`:

```json
{
  "status": "ok",
  "total": 42,
  "chunks": 318,
  "errors": 0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total` | int | Documents processed from `aws_docs_cache` |
| `chunks` | int | Total vector chunks indexed |
| `errors` | int | Documents that failed to index |

**Errors:**

| Status | Condition |
|--------|-----------|
| `403` | Non-admin user |
| `503` | PostgreSQL or vector store not available |

Implementation: `services/vector/indexer.py` → `index_all_cached()`

---

## Error Response Format

FastAPI returns errors as JSON with a `detail` field:

```json
{
  "detail": "Authentication required"
}
```

For validation errors (`422`), `detail` is an array of field-level errors.

---

## CORS

Configured in `apps/api/main.py`:

| Setting | Value |
|---------|-------|
| Allowed origins | `http://localhost:8501` |
| Credentials | Allowed |
| Methods | All |
| Headers | All |

---

## Example: Full Client Flow

```powershell
# 1. Register
curl -X POST http://localhost:8000/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email": "dev@example.com", "password": "secret123"}'

# 2. Login
$response = curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email": "dev@example.com", "password": "secret123"}' | ConvertFrom-Json

$token = $response.access_token

# 3. Chat
curl -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $token" `
  -d '{"query": "What are Lambda timeout limits?"}'

# 4. Continue conversation (reuse session_id from previous response)
curl -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $token" `
  -d '{"query": "Can I increase it?", "session_id": "<session_id>"}'
```

---

## Streamlit UI Integration

The Streamlit app (`apps/ui/app.py`) uses the same API:

| UI action | API call |
|-----------|----------|
| Register | `POST /auth/register` |
| Login | `POST /auth/login` → stores `access_token` in session state |
| Send message | `POST /chat` with Bearer header |
| Session expired | Handles `401` → redirects to login |
| Rate limited | Handles `429` → shows warning |

Environment variable: `API_URL` (default `http://localhost:8000`).

---

## Related Documentation

- [System Architecture](system-architecture.md)
- [AI / RAG Strategy](ai-rag-strategy.md)
- [Deployment Strategy](deployment-strategy.md)
