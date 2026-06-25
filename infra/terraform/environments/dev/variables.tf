variable "project_name" {
  type    = string
  default = "aws-docs-bot"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "az_count" {
  type    = number
  default = 2
}

variable "enable_nat_gateway" {
  type    = bool
  default = true
}

# ── Database ──────────────────────────────────────────────────────────────────

variable "db_name" {
  type    = string
  default = "aws_docs"
}

variable "db_username" {
  type    = string
  default = "postgres"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "rds_multi_az" {
  type    = bool
  default = false
}

variable "rds_skip_final_snapshot" {
  type    = bool
  default = true
}

# ── OpenSearch ────────────────────────────────────────────────────────────────

variable "opensearch_instance_type" {
  type    = string
  default = "t3.small.search"
}

variable "opensearch_instance_count" {
  type    = number
  default = 1
}

variable "opensearch_index" {
  type    = string
  default = "aws_docs"
}

# ── Bedrock ───────────────────────────────────────────────────────────────────

variable "bedrock_model_id" {
  type    = string
  default = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "bedrock_embed_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

# ── ECS ───────────────────────────────────────────────────────────────────────

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "api_cpu" {
  type    = string
  default = "1024"
}

variable "api_memory" {
  type    = string
  default = "2048"
}

variable "ui_cpu" {
  type    = string
  default = "512"
}

variable "ui_memory" {
  type    = string
  default = "1024"
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "ui_desired_count" {
  type    = number
  default = 1
}

# ── DNS (optional) ────────────────────────────────────────────────────────────

variable "route53_zone_id" {
  type    = string
  default = ""
}

variable "domain_name" {
  type    = string
  default = ""
}

variable "enable_https" {
  type    = bool
  default = false
}

# ── CI/CD ─────────────────────────────────────────────────────────────────────

variable "enable_github_oidc" {
  type    = bool
  default = false
}

variable "github_repo" {
  type    = string
  default = "samyak-bhagat/aws_documentation_bot"
}

variable "ecr_force_delete" {
  type    = bool
  default = true
}
