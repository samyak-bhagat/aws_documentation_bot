# Production Environment

project_name  = "aws-docs-bot"
environment   = "prod"
aws_region    = "us-east-1"

vpc_cidr           = "10.0.0.0/16"
az_count           = 2
enable_nat_gateway = true

# Production database settings
db_name            = "aws_docs"
rds_instance_class = "db.t3.small"
rds_multi_az       = true
rds_skip_final_snapshot = false

opensearch_instance_type  = "t3.medium.search"
opensearch_instance_count = 3

bedrock_model_id       = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
bedrock_embed_model_id = "amazon.titan-embed-text-v2:0"

image_tag = "latest"

# Route 53 — configure with your domain
route53_zone_id = ""
domain_name     = ""

# GitHub OIDC deploy role
enable_github_oidc = true
github_repo        = "samyak-bhagat/aws_documentation_bot"

ecr_force_delete = false

# ECS task counts for production
api_desired_count = 2
ui_desired_count  = 2
