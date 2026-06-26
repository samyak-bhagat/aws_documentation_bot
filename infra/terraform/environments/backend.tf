# Backend configuration for remote state management
# 
# Usage:
# 1. For local state (development):
#    terraform init
#
# 2. For remote S3 state (after bootstrap):
#    terraform init -backend-config="bucket=aws-docs-bot-terraform-state-ACCOUNT_ID" \
#                   -backend-config="key=${ENVIRONMENT}/terraform.tfstate"
#
# Or create environment-specific backend files:
#    terraform init -backend-config="backend-dev.tfbackend"
#    terraform init -backend-config="backend-prod.tfbackend"

# Backend files (create these after bootstrap):
# backend-dev.tfbackend:
#   bucket         = "aws-docs-bot-terraform-state-ACCOUNT_ID"
#   key            = "dev/terraform.tfstate"
#   region         = "us-east-1"
#   dynamodb_table = "aws-docs-bot-terraform-lock"
#   encrypt        = true
#
# backend-prod.tfbackend:
#   bucket         = "aws-docs-bot-terraform-state-ACCOUNT_ID"
#   key            = "prod/terraform.tfstate"
#   region         = "us-east-1"
#   dynamodb_table = "aws-docs-bot-terraform-lock"
#   encrypt        = true
#
# backend-staging.tfbackend:
#   bucket         = "aws-docs-bot-terraform-state-ACCOUNT_ID"
#   key            = "staging/terraform.tfstate"
#   region         = "us-east-1"
#   dynamodb_table = "aws-docs-bot-terraform-lock"
#   encrypt        = true
