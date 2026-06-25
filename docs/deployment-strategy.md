# Deployment Strategy

This document covers how to deploy the AWS Documentation Assistant — from local Docker Compose to AWS ECS Fargate provisioned by Terraform.

All commands and configuration values are taken from the repository implementation.

---

## Deployment Options

| Environment | Method | Best for |
|-------------|--------|----------|
| **Local (minimal)** | Python venv + uvicorn | Agent development, MCP testing |
| **Local (full stack)** | Docker Compose | Integration testing with DB + vector search + UI |
| **AWS (dev)** | Terraform + ECS Fargate | Production-like deployment on AWS |
| **CI/CD** | GitHub Actions | Automated test, build, and deploy on push to `main` |

---

## Local Deployment

### Minimal (API + MCP only)

**Requirements:** Python 3.12, OpenAI API key, `uv` for MCP server.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install uv

copy .env.example .env
# Set OPENAI_API_KEY in .env

uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Limitations without `DATABASE_URL`:**

- Auth endpoints return 503
- `/chat` requires JWT (cannot authenticate without DB)
- No chat memory or doc cache persistence
- No vector search (unless `QDRANT_URL` set with external Qdrant)

**Workaround for agent testing:** Use the CLI instead:

```powershell
python -m agents.graph.builder "What are Lambda timeout limits?"
```

### Full Stack (Docker Compose)

**File:** `infra/docker/docker-compose.yml`

```powershell
cd infra/docker
docker compose up --build
```

**Services started:**

| Service | Image / Build | Port | Purpose |
|---------|---------------|------|---------|
| `api` | `Dockerfile.api` | 8000 | FastAPI + MCP (uvx pre-cached at build) |
| `ui` | `Dockerfile.ui` | 8501 | Streamlit chat UI |
| `postgres` | `postgres:16-alpine` | 5432 | Document cache, chat memory, users |
| `qdrant` | `qdrant/qdrant:latest` | 6333 | Vector search index |

**Environment overrides in compose:**

```yaml
DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/aws_docs
QDRANT_URL: http://qdrant:6333
API_URL: http://api:8000  # UI service only
```

Uses `.env` from project root via `env_file: ../../.env`.

**First-time setup after compose is running:**

1. Open http://localhost:8501
2. Register a user account
3. Ask a question — first queries use MCP; subsequent queries benefit from cache

---

## Docker Images

### API Image

**File:** `infra/docker/Dockerfile.api`

```dockerfile
FROM python:3.12-slim
# Installs uv, requirements.txt, pre-caches MCP server via uvx
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build:

```powershell
docker build -f infra/docker/Dockerfile.api -t aws-docs-api .
```

### UI Image

**File:** `infra/docker/Dockerfile.ui`

```dockerfile
FROM python:3.12-slim
# Minimal: streamlit + requests, copies apps/ui/app.py only
CMD ["streamlit", "run", "apps/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build:

```powershell
docker build -f infra/docker/Dockerfile.ui -t aws-docs-ui .
```

---

## AWS Deployment (Terraform)

Full step-by-step guide: [`infra/terraform/README.md`](../infra/terraform/README.md)

### Architecture

```mermaid
flowchart TB
    User[User] --> ALB[Application Load Balancer]
    ALB -->|port 8000| API[ECS Fargate<br/>API task]
    ALB -->|port 8501| UI[ECS Fargate<br/>UI task]

    API --> RDS[(RDS PostgreSQL 16)]
    API --> OS[(OpenSearch<br/>k-NN index)]
    API --> Bedrock[Amazon Bedrock<br/>Claude + Titan Embed]
    API --> MCP[AWS Docs MCP Server<br/>via uvx in container]
    UI --> API

    ECR[ECR Repositories] -.->|images| API
    ECR -.->|images| UI
    SM[Secrets Manager] -.->|DATABASE_URL, JWT_SECRET| API
```

### Terraform Modules

**Environment:** `infra/terraform/environments/dev/`

| Module | Resources |
|--------|-----------|
| `vpc` | VPC, public/private subnets, IGW, NAT Gateway |
| `ecr` | API and UI container repositories (scan on push) |
| `rds` | PostgreSQL 16 (private subnet) |
| `opensearch` | k-NN vector domain (private subnet) |
| `alb` | Application Load Balancer, target groups |
| `ecs` | Fargate cluster, API + UI services |
| `iam` | ECS task/execution roles, optional GitHub OIDC role |
| `secrets` | Secrets Manager for DB and JWT |

### Provisioned Resources

From `infra/terraform/environments/dev/main.tf`:

- Random passwords for DB, JWT, and OpenSearch master user
- Secrets Manager secrets with connection strings
- Security groups: ALB → ECS tasks (ports 8000, 8501)
- ECS tasks in private subnets (or public if NAT disabled)
- Route 53 alias record (optional, when `route53_zone_id` set)

### Key Terraform Outputs

```powershell
cd infra/terraform/environments/dev
terraform output alb_dns_name          # Application URL
terraform output ecr_api_repository_url
terraform output ecr_ui_repository_url
terraform output github_actions_role_arn
terraform output aws_account_id
```

### Bootstrap (One-Time)

```powershell
cd infra/terraform/bootstrap
terraform init
terraform apply
# Note state_bucket_name and lock_table_name
# Uncomment backend "s3" block in environments/dev/main.tf
# terraform init -migrate-state
```

First `terraform apply` in dev takes **20–40 minutes** (OpenSearch and RDS are slow to provision).

### Environment Variables on ECS

Injected by the ECS module (`infra/terraform/modules/ecs/`) from Secrets Manager and Terraform variables:

| Variable | Source |
|----------|--------|
| `DATABASE_URL` | Secrets Manager (`db` secret) |
| `JWT_SECRET` | Secrets Manager (`jwt` secret) |
| `OPENSEARCH_ENDPOINT` | Terraform output (HTTPS domain endpoint) |
| `OPENSEARCH_INDEX` | `var.opensearch_index` |
| `BEDROCK_MODEL_ID` | `var.bedrock_model_id` |
| `BEDROCK_EMBED_MODEL_ID` | `var.bedrock_embed_model_id` |
| `AWS_REGION` | `var.aws_region` |

When `BEDROCK_MODEL_ID` is set, the application automatically uses Bedrock for LLM and Titan for embeddings. OpenSearch replaces Qdrant.

### Pre-Deploy Checklist

1. **Enable Bedrock models** in AWS Console (Claude + Titan Embed Text v2) in the deployment region
2. **Configure AWS CLI** with credentials (`aws configure`)
3. **Copy and edit** `terraform.tfvars.example` → `terraform.tfvars`
4. **Apply Terraform** to create infrastructure
5. **Build and push** Docker images to ECR
6. **Force ECS deployment** to pull new images

### Push Images to ECR

```powershell
$ACCOUNT = terraform output -raw aws_account_id
$REGION  = terraform output -raw aws_region
$API_ECR = terraform output -raw ecr_api_repository_url
$UI_ECR  = terraform output -raw ecr_ui_repository_url

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

docker build -f infra/docker/Dockerfile.api -t "${API_ECR}:latest" .
docker push "${API_ECR}:latest"

docker build -f infra/docker/Dockerfile.ui -t "${UI_ECR}:latest" .
docker push "${UI_ECR}:latest"

aws ecs update-service --cluster aws-docs-bot-dev-cluster --service aws-docs-bot-dev-api --force-new-deployment --region $REGION
aws ecs update-service --cluster aws-docs-bot-dev-cluster --service aws-docs-bot-dev-ui --force-new-deployment --region $REGION
```

### Verify Deployment

```powershell
# Health check
curl http://<alb-dns>/health

# UI
# Open http://<alb-dns>/ in browser
```

---

## CI/CD Pipelines

### CI (`.github/workflows/ci.yml`)

**Trigger:** Push or PR to `main`

```mermaid
flowchart LR
    Push[Push / PR] --> Lint[Ruff lint + format check]
    Lint --> MyPy[MyPy type check]
    MyPy --> Test[pytest unit tests + coverage]
    Test --> Docker[Docker build API image]
```

| Job | Python | Steps |
|-----|--------|-------|
| `lint` | 3.12 | `ruff check .`, `ruff format --check .` |
| `type-check` | 3.12 | `mypy services/ agents/ apps/ core/` |
| `test` | 3.12 | `pytest tests/unit/ -v --cov=. --cov-report=term-missing` |
| `docker-build` | — | `docker build -f infra/docker/Dockerfile.api` |

**Secrets:** `OPENAI_API_KEY` (for tests that need it)

### Deploy (`.github/workflows/deploy.yml`)

**Trigger:** Push to `main` or `workflow_dispatch`

```mermaid
flowchart LR
    Push[Push to main] --> Test[Lint + pytest]
    Test --> Build[Build + push API + UI to ECR]
    Build --> Deploy[Force ECS rolling deployment]
    Deploy --> Wait[Wait for services stable]
```

| Job | Condition | Actions |
|-----|-----------|---------|
| `test` | Always | Ruff + pytest |
| `build-and-push` | `main` branch only | Docker build → ECR push (tagged with SHA + `latest`) |
| `deploy` | `main` branch only | `aws ecs update-service --force-new-deployment` for API and UI |

**Environment variables (workflow):**

```yaml
AWS_REGION: us-east-1
ECR_API_REPO: aws-docs-bot-dev-api
ECR_UI_REPO: aws-docs-bot-dev-ui
ECS_CLUSTER: aws-docs-bot-dev-cluster
ECS_API_SERVICE: aws-docs-bot-dev-api
ECS_UI_SERVICE: aws-docs-bot-dev-ui
```

**Secrets:**

| Secret | Purpose |
|--------|---------|
| `OPENAI_API_KEY` | CI test execution |
| `AWS_ROLE_ARN` | OIDC role for ECR push and ECS deploy |

**Enable OIDC deploy:**

1. Set `enable_github_oidc = true` in `terraform.tfvars`
2. Run `terraform apply`
3. Add `AWS_ROLE_ARN` GitHub secret from `terraform output github_actions_role_arn`

---

## Environment Configuration Matrix

| Variable | Local minimal | Docker Compose | AWS ECS |
|----------|---------------|----------------|---------|
| `OPENAI_API_KEY` | Required | Required | Not set (uses Bedrock) |
| `BEDROCK_MODEL_ID` | — | — | Required |
| `DATABASE_URL` | Optional | Auto-set by compose | From Secrets Manager |
| `QDRANT_URL` | Optional | Auto-set by compose | Not set (uses OpenSearch) |
| `OPENSEARCH_ENDPOINT` | — | — | From Terraform |
| `JWT_SECRET` | Default (insecure) | From `.env` | From Secrets Manager |
| `MCP_SERVER_COMMAND` | `uvx` | `uvx` | `uvx` (pre-cached in image) |

---

## Post-Deploy Operations

### Trigger knowledge sync

```powershell
# Requires admin JWT
curl -X POST http://<host>/admin/sync `
  -H "Authorization: Bearer <admin_token>"
```

### Re-index vector store

```powershell
curl -X POST http://<host>/admin/reindex `
  -H "Authorization: Bearer <admin_token>"
```

Run after initial deployment to populate OpenSearch from any cached documents.

### View logs

- **Local:** JSON structured logs to stdout (via `core/logging.py`)
- **ECS:** CloudWatch Logs (configured in ECS task definition module)

---

## Estimated AWS Cost (Dev)

From `infra/terraform/README.md` (us-east-1):

| Service | Approx. monthly |
|---------|-----------------|
| NAT Gateway | ~$32 |
| OpenSearch t3.small | ~$26 |
| RDS db.t4g.micro | ~$12 |
| ECS Fargate (2 tasks) | ~$30 |
| ALB | ~$18 |
| **Total** | **~$120** |

Set `enable_nat_gateway = false` to reduce cost (tasks run in public subnets — not recommended for production).

---

## Security Notes

- Never commit `.env`, `*accessKeys*.csv`, or `terraform.tfvars` (all in `.gitignore`)
- Prefer GitHub OIDC over long-lived AWS access keys for CI/CD
- Rotate access keys if ever exposed
- OpenSearch master password is generated by Terraform — use Secrets Manager for production
- Change default `JWT_SECRET` before any non-local deployment
- ECS tasks run in private subnets with egress via NAT Gateway

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `503 Agent not initialised` | MCP server failed to start | Check `uvx` is installed; verify MCP args in `.env` |
| `503 Database not available` | `DATABASE_URL` not set or PostgreSQL down | Start postgres service or set connection string |
| `401 Authentication required` | Missing Bearer token on `/chat` | Login first, include `Authorization` header |
| Hybrid search not used | Vector index empty | Run `/admin/sync` then `/admin/reindex` |
| ECS tasks unhealthy | Image not pushed or env vars missing | Push to ECR, verify Secrets Manager values |
| Bedrock errors | Model access not enabled | Enable models in Bedrock console for deployment region |

---

## Related Documentation

- [System Architecture](system-architecture.md)
- [API Documentation](api.md)
- [AI / RAG Strategy](ai-rag-strategy.md)
- [Terraform README](../infra/terraform/README.md)
