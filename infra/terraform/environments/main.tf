terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # S3 backend configuration — use `terraform init -backend-config` or .tfbackend files
  # Uncomment after bootstrap apply — see infra/terraform/README.md
  # backend "s3" {
  #   region         = "us-east-1"
  #   dynamodb_table = "aws-docs-bot-terraform-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
}

# ── 1. VPC ───────────────────────────────────────────────────────────────────

module "vpc" {
  source = "../modules/vpc"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  enable_nat_gateway = var.enable_nat_gateway
}

# ── 2. App security group (ECS tasks) ─────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-app-sg"
  description = "Application tier (ECS tasks)"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-app-sg"
  }
}

# ── 3. ECR ────────────────────────────────────────────────────────────────────

module "ecr" {
  source = "../modules/ecr"

  name_prefix  = local.name_prefix
  force_delete = var.ecr_force_delete
}

# ── 4. Secrets ────────────────────────────────────────────────────────────────

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "jwt" {
  length  = 48
  special = true
}

resource "random_password" "opensearch" {
  length  = 24
  special = true
}

resource "aws_secretsmanager_secret" "db" {
  name = "${local.name_prefix}/database"
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "${local.name_prefix}/jwt"
}

resource "aws_secretsmanager_secret" "opensearch" {
  name = "${local.name_prefix}/opensearch"
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id
  secret_string = jsonencode({
    jwt_secret = random_password.jwt.result
  })
}

# ── 5. IAM (roles before OpenSearch domain) ───────────────────────────────────

module "iam" {
  source = "../modules/iam"

  name_prefix        = local.name_prefix
  secret_arns        = [aws_secretsmanager_secret.db.arn, aws_secretsmanager_secret.jwt.arn, aws_secretsmanager_secret.opensearch.arn]
  enable_github_oidc = var.enable_github_oidc
  github_repo        = var.github_repo
}

# ── 6. RDS ────────────────────────────────────────────────────────────────────

module "rds" {
  source = "../modules/rds"

  name_prefix           = local.name_prefix
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  db_name               = var.db_name
  db_username           = var.db_username
  db_password           = random_password.db.result
  instance_class        = var.rds_instance_class
  multi_az              = var.rds_multi_az
  skip_final_snapshot   = var.rds_skip_final_snapshot
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    engine   = "postgres"
    host     = module.rds.endpoint
    port     = module.rds.port
    dbname   = var.db_name
    url      = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${module.rds.endpoint}:${module.rds.port}/${var.db_name}"
  })

  depends_on = [module.rds]
}

# ── 7. OpenSearch ─────────────────────────────────────────────────────────────

module "opensearch" {
  source = "../modules/opensearch"

  name_prefix            = local.name_prefix
  domain_name            = replace("${local.name_prefix}-search", "-", "")
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  app_security_group_id  = aws_security_group.app.id
  aws_region             = var.aws_region
  aws_account_id         = local.account_id
  allowed_principal_arns = [module.iam.ecs_task_role_arn]
  master_user_password   = random_password.opensearch.result
  instance_type          = var.opensearch_instance_type
  instance_count         = var.opensearch_instance_count
}

resource "aws_secretsmanager_secret_version" "opensearch" {
  secret_id = aws_secretsmanager_secret.opensearch.id
  secret_string = jsonencode({
    username = "admin"
    password = random_password.opensearch.result
  })

  depends_on = [module.opensearch]
}

resource "aws_iam_role_policy" "ecs_task_opensearch" {
  name = "${local.name_prefix}-ecs-task-opensearch"
  role = module.iam.ecs_task_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "es:ESHttpGet",
        "es:ESHttpPut",
        "es:ESHttpPost",
        "es:ESHttpDelete",
        "es:ESHttpHead",
        "es:ESHttpPatch"
      ]
      Resource = "${module.opensearch.domain_arn}/*"
    }]
  })
}

# ── 8. ALB ────────────────────────────────────────────────────────────────────

module "alb" {
  source = "../modules/alb"

  name_prefix       = local.name_prefix
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  enable_https      = var.enable_https
}

resource "aws_security_group_rule" "app_from_alb_api" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app.id
  source_security_group_id = module.alb.alb_security_group_id
  description              = "API from ALB"
}

resource "aws_security_group_rule" "app_from_alb_ui" {
  type                     = "ingress"
  from_port                = 8501
  to_port                  = 8501
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app.id
  source_security_group_id = module.alb.alb_security_group_id
  description              = "UI from ALB"
}

# ── 9. ECS ────────────────────────────────────────────────────────────────────

module "ecs" {
  source = "../modules/ecs"

  name_prefix           = local.name_prefix
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = var.enable_nat_gateway ? module.vpc.private_subnet_ids : module.vpc.public_subnet_ids
  app_security_group_id = aws_security_group.app.id
  api_target_group_arn  = module.alb.api_target_group_arn
  ui_target_group_arn   = module.alb.ui_target_group_arn
  execution_role_arn    = module.iam.ecs_task_execution_role_arn
  task_role_arn         = module.iam.ecs_task_role_arn
  aws_region            = var.aws_region
  assign_public_ip      = !var.enable_nat_gateway

  api_image = "${module.ecr.api_repository_url}:${var.image_tag}"
  ui_image  = "${module.ecr.ui_repository_url}:${var.image_tag}"

  db_secret_arn          = aws_secretsmanager_secret.db.arn
  jwt_secret_arn         = aws_secretsmanager_secret.jwt.arn
  opensearch_secret_arn  = aws_secretsmanager_secret.opensearch.arn
  opensearch_endpoint    = "https://${module.opensearch.endpoint}"
  opensearch_index       = var.opensearch_index
  bedrock_model_id       = var.bedrock_model_id
  bedrock_embed_model_id = var.bedrock_embed_model_id
  internal_api_url       = module.alb.alb_dns_name

  api_cpu           = var.api_cpu
  api_memory        = var.api_memory
  ui_cpu            = var.ui_cpu
  ui_memory         = var.ui_memory
  api_desired_count = var.api_desired_count
  ui_desired_count  = var.ui_desired_count

  depends_on = [
    aws_security_group_rule.app_from_alb_api,
    aws_security_group_rule.app_from_alb_ui,
  ]
}

# ── 10. Route 53 (optional) ───────────────────────────────────────────────────

resource "aws_route53_record" "app" {
  count = var.route53_zone_id != "" ? 1 : 0

  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.alb.alb_dns_name
    zone_id                = module.alb.alb_zone_id
    evaluate_target_health = true
  }
}
