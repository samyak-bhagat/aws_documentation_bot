variable "project_name" {
  description = "Project name used as a prefix for shared resources."
  type        = string
  default     = "aws-docs-bot"
}

variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}
