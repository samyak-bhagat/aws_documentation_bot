# Post-Deploy Runbook

Complete these steps after merging **Phase 9** (`refactor/aws-native-production-hardening`) and before relying on production traffic.

---

## Checklist Overview

| # | Step | Where | Automated in repo? |
|---|------|-------|-------------------|
| 1 | Apply Terraform (ALB `/health/ready`, ECS `APP_ENV=production`) | AWS | Config in Terraform |
| 2 | Enable Bedrock models | AWS Console | Manual |
| 3 | Verify AWS access (Bedrock invoke) | Local CLI | `scripts/check_aws_access.py` |
| 4 | Build & push Docker images | ECR | Manual or GitHub Actions |
| 5 | Force ECS deployment | AWS CLI | Manual or GitHub Actions |
| 6 | Remove obsolete GitHub secret `OPENAI_API_KEY` | GitHub | Manual |
| 7 | Confirm readiness endpoint | ALB URL | Manual |
| 8 | Bootstrap data (register user, sync, reindex) | API | Manual |

---

## 1. Apply Terraform changes

Phase 9 updated:

- **ECS API task** — `APP_ENV=production` (strict config validation)
- **ECS API container** — health check against `http://127.0.0.1:8000/health/ready`
- **ALB target group** — health check path `/health/ready` (returns 503 until MCP + RDS + OpenSearch are up)

```powershell
cd infra/terraform/environments/dev
terraform plan
terraform apply
```

Review the plan for:

- `aws_lb_target_group.api` — health_check path change
- `aws_ecs_task_definition.api` — new revision with `APP_ENV` and `healthCheck`

After apply, ECS services pick up the new task definition on the next deployment (Step 5).

---

## 2. Enable Bedrock models

The application **requires** Bedrock — there is no OpenAI fallback.

1. Open [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/) in your deployment region (default `us-east-1`).
2. Go to **Model access** (or **Chat / Text** model catalog, depending on console version).
3. Enable:
   - **Anthropic Claude** — must match `bedrock_model_id` in `terraform.tfvars` (default: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`)
   - **Amazon Titan Text Embeddings V2** — `amazon.titan-embed-text-v2:0`
4. Wait until access status shows **Access granted**.

Verify the model IDs in `infra/terraform/environments/dev/terraform.tfvars` match what you enabled.

---

## 3. Verify AWS credentials and Bedrock invoke

```powershell
aws configure   # or use SSO / instance role
python scripts/check_aws_access.py
```

Expected: `"bedrock_invoke": { "ok": true, ... }`. If you see `AccessDeniedException`, return to Step 2.

---

## 4. Build and push images

If not using GitHub Actions deploy:

```powershell
cd infra/terraform/environments/dev
$ACCOUNT = terraform output -raw aws_account_id
$REGION  = terraform output -raw aws_region
$API_ECR = terraform output -raw ecr_api_repository_url
$UI_ECR  = terraform output -raw ecr_ui_repository_url

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

docker build -f infra/docker/Dockerfile.api -t "${API_ECR}:latest" .
docker push "${API_ECR}:latest"

docker build -f infra/docker/Dockerfile.ui -t "${UI_ECR}:latest" .
docker push "${UI_ECR}:latest"
```

---

## 5. Deploy to ECS

```powershell
$REGION = terraform output -raw aws_region
aws ecs update-service --cluster aws-docs-bot-dev-cluster --service aws-docs-bot-dev-api --force-new-deployment --region $REGION
aws ecs update-service --cluster aws-docs-bot-dev-cluster --service aws-docs-bot-dev-ui --force-new-deployment --region $REGION
aws ecs wait services-stable --cluster aws-docs-bot-dev-cluster --services aws-docs-bot-dev-api aws-docs-bot-dev-ui --region $REGION
```

Or push to `main` with GitHub Actions deploy enabled (`enable_github_oidc = true`, secret `AWS_ROLE_ARN` set).

---

## 6. Remove `OPENAI_API_KEY` from GitHub Secrets

Phase 9 removed all OpenAI usage. CI and deploy workflows no longer reference this secret.

**GitHub UI:**

1. Repository → **Settings** → **Secrets and variables** → **Actions**
2. Find `OPENAI_API_KEY` → **Remove**

**GitHub CLI** (if installed):

```powershell
gh secret delete OPENAI_API_KEY
```

**Secrets still required:**

| Secret | Purpose |
|--------|---------|
| `AWS_ROLE_ARN` | OIDC deploy to ECR + ECS |

---

## 7. Verify deployment

Replace `<alb-dns>` with `terraform output -raw alb_dns_name` (strip `http://` if present).

```powershell
# Readiness — must return 200 with all dependencies true
curl http://<alb-dns>/health/ready

# Liveness — always 200 when process is up
curl http://<alb-dns>/health
```

Example healthy readiness response:

```json
{
  "status": "ok",
  "mcp_connected": true,
  "database_connected": true,
  "vector_store_connected": true,
  "scheduler_running": true
}
```

If `/health/ready` returns **503**, check CloudWatch logs:

- Log group: `/ecs/aws-docs-bot-dev/api`
- Common causes: Bedrock model not enabled, OpenSearch security group, RDS unreachable, MCP startup failure

---

## 8. Bootstrap application data

```powershell
# Register first user
curl -X POST http://<alb-dns>/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email": "admin@example.com", "password": "your-secure-password"}'

# Login → get access_token, then promote to admin in RDS if needed:
# UPDATE users SET is_admin = true WHERE email = 'admin@example.com';

# Trigger knowledge sync (requires admin JWT)
curl -X POST http://<alb-dns>/admin/sync -H "Authorization: Bearer <admin_token>"

# Re-index cached docs into OpenSearch (requires admin JWT)
curl -X POST http://<alb-dns>/admin/reindex -H "Authorization: Bearer <admin_token>"
```

Open the Streamlit UI at `http://<alb-dns>/` and log in.

---

## Next steps (recommended)

| Priority | Task | Why |
|----------|------|-----|
| High | Enable HTTPS on ALB (`enable_https` + ACM cert in Terraform) | TLS for production |
| High | Create first admin user + run `/admin/sync` + `/admin/reindex` | Populate OpenSearch index |
| Medium | Set up nightly integration workflow (Bedrock/OpenSearch smoke tests) | Catch regressions |
| Medium | Configure `OTEL_EXPORTER_OTLP_ENDPOINT` for trace export | Production observability |
| Low | Add Route 53 custom domain | Friendly URL |
| Low | WAF on ALB | Edge rate limiting / bot protection |

See also: [`deployment-strategy.md`](deployment-strategy.md), [`infra/terraform/README.md`](../infra/terraform/README.md).
