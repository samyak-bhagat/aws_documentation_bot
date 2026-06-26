# AWS Infrastructure (Terraform)

Provisions the full AWS stack from scratch for the AWS Documentation Bot:

| Resource | Service |
|----------|---------|
| Network | VPC, public/private subnets, IGW, NAT Gateway |
| Compute | ECS Fargate (API + Streamlit UI) |
| Load balancer | Application Load Balancer |
| Database | RDS PostgreSQL 16 |
| Vector search | Amazon OpenSearch Service |
| LLM / embeddings | Amazon Bedrock (IAM — enable models in console) |
| Images | ECR (scan on push) |
| Secrets | Secrets Manager |
| DNS | Route 53 (optional) |

## Prerequisites

1. **AWS CLI** installed and configured with your access keys:
   ```powershell
   aws configure
   # Access Key ID + Secret from your local CSV (never commit the CSV)
   ```

2. **Terraform** >= 1.6 — https://developer.hashicorp.com/terraform/install

3. **Enable Bedrock models** in AWS Console (required — app uses Bedrock only):
   - Amazon Bedrock → Model access → enable models matching `terraform.tfvars`:
     - Chat: `bedrock_model_id` (default Claude Sonnet 4.5)
     - Embeddings: `amazon.titan-embed-text-v2:0`
   - Region must match `aws_region` (default `us-east-1`)
   - Verify: `python scripts/check_aws_access.py`

4. **Docker** — for building and pushing images to ECR

## Multi-Environment Setup

All environments (dev, staging, prod) use the same Terraform configuration with environment-specific `.tfvars` files.

Available environments:
- `terraform.dev.tfvars` — Development (minimal resources)
- `terraform.staging.tfvars` — Staging (balanced resources)
- `terraform.prod.tfvars` — Production (high availability, multi-AZ)

## Step 1 — Bootstrap remote state (one time, optional)

For local development, skip this step. For production with remote state:

```powershell
cd infra/terraform/bootstrap
terraform init
terraform apply
```

Note the outputs: `state_bucket_name`, `lock_table_name`, `aws_account_id`.

Create backend configuration files in `infra/terraform/environments/`:

**backend-dev.tfbackend:**
```hcl
bucket         = "aws-docs-bot-terraform-state-ACCOUNT_ID"
key            = "dev/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "aws-docs-bot-terraform-lock"
encrypt        = true
```

**backend-prod.tfbackend:** (replace `dev` with `prod` or `staging`)

Then initialize with the backend config:
```powershell
cd ../environments
terraform init -backend-config="backend-dev.tfbackend"
```

For the first run, you can skip bootstrap and use **local state** (no backend configuration needed).

## Step 2 — Deploy infrastructure (any environment)

```powershell
cd infra/terraform/environments

# For development
terraform init
terraform plan -var-file="terraform.dev.tfvars"
terraform apply -var-file="terraform.dev.tfvars"

# For staging
terraform plan -var-file="terraform.staging.tfvars"
terraform apply -var-file="terraform.staging.tfvars"

# For production
terraform plan -var-file="terraform.prod.tfvars"
terraform apply -var-file="terraform.prod.tfvars"
```

First `apply` takes **20–40 minutes** (OpenSearch + RDS are slow).

Save outputs for your environment:
```powershell
terraform output -var-file="terraform.dev.tfvars" alb_dns_name
terraform output -var-file="terraform.dev.tfvars" ecr_api_repository_url
```

## Step 3 — Build and push Docker images

After ECR repos exist (from `terraform apply`):

```powershell
# Use your environment's output variables
$ENV = "dev"  # or "staging", "prod"
$ACCOUNT = terraform output -raw aws_account_id
$REGION  = terraform output -raw aws_region
$API_ECR = terraform output -raw ecr_api_repository_url
$UI_ECR  = terraform output -raw ecr_ui_repository_url

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

docker build -f infra/docker/Dockerfile.api -t "${API_ECR}:latest" .
docker push "${API_ECR}:latest"

docker build -f infra/docker/Dockerfile.ui -t "${UI_ECR}:latest" .
docker push "${UI_ECR}:latest"

# Force ECS to pull new images
$CLUSTER = "aws-docs-bot-${ENV}-cluster"
aws ecs update-service --cluster $CLUSTER --service "aws-docs-bot-${ENV}-api" --force-new-deployment --region $REGION
aws ecs update-service --cluster $CLUSTER --service "aws-docs-bot-${ENV}-ui" --force-new-deployment --region $REGION
```

## Step 4 — Verify deployment

Open the ALB URL from `terraform output alb_dns_name`.

```powershell
$ALB = terraform output -raw alb_dns_name
curl "$ALB/health/ready"
curl "$ALB/health"
```

- UI: `http://<alb-dns>/`
- API readiness: `http://<alb-dns>/health/ready` (must return **200** with all dependencies `true`)
- API liveness: `http://<alb-dns>/health`

Run the AWS/Bedrock sanity check locally:

```powershell
python scripts/check_aws_access.py
```

## Step 5 — GitHub Actions deploy (optional)

1. Update your environment's `.tfvars` file to enable GitHub OIDC:
   ```hcl
   enable_github_oidc = true
   ```
2. Re-run `terraform apply -var-file="terraform.prod.tfvars"` (or your environment)
3. Add GitHub secret: `AWS_ROLE_ARN` = output `github_actions_role_arn`
4. **Remove** obsolete secret `OPENAI_API_KEY` (no longer used after Phase 9)
5. Push to `main` — `.github/workflows/deploy.yml` builds and deploys

Full post-deploy checklist: [`docs/post-deploy-runbook.md`](../../docs/post-deploy-runbook.md)

## Phase 9 infrastructure notes

After merging AWS-native Phase 9, re-run `terraform apply` to pick up:

| Resource | Change |
|----------|--------|
| ECS API task | `APP_ENV=production`, container health check on `/health/ready` |
| ALB API target group | Health check path `/health/ready` |

ECS task definition sets `APP_ENV=production` — the API **will not start** if Bedrock, OpenSearch, or RDS configuration is missing or invalid.

## Estimated monthly cost (dev, us-east-1)

| Service | Approx. |
|---------|---------|
| NAT Gateway | ~$32 |
| OpenSearch t3.small | ~$26 |
| RDS db.t4g.micro | ~$12 |
| ECS Fargate (2 tasks) | ~$30 |
| ALB | ~$18 |
| **Total** | **~$120/month** |

Use `enable_nat_gateway = false` only if tasks run in public subnets (not recommended).

## Security notes

- `*accessKeys*.csv` is in `.gitignore` — never commit AWS keys
- Rotate access keys if they were ever exposed
- Prefer GitHub OIDC over long-lived keys for CI
- OpenSearch master password is generated by Terraform (stored in state — use Secrets Manager for prod)

## Directory layout

```
infra/terraform/
├── bootstrap/          # S3 + DynamoDB for remote state
├── environments/dev/   # Dev stack (wire-up)
└── modules/
    ├── vpc/
    ├── ecr/
    ├── rds/
    ├── opensearch/
    ├── alb/
    ├── ecs/
    └── iam/
```
