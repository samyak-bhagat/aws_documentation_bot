variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "app_security_group_id" {
  type = string
}

variable "api_target_group_arn" {
  type = string
}

variable "ui_target_group_arn" {
  type = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "api_image" {
  type = string
}

variable "ui_image" {
  type = string
}

variable "db_secret_arn" {
  type = string
}

variable "jwt_secret_arn" {
  type = string
}

variable "opensearch_endpoint" {
  type = string
}

variable "opensearch_index" {
  type    = string
  default = "aws_docs"
}

variable "bedrock_model_id" {
  type = string
}

variable "bedrock_embed_model_id" {
  type = string
}

variable "internal_api_url" {
  type        = string
  description = "URL the Streamlit UI uses to reach the API."
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

variable "assign_public_ip" {
  type    = bool
  default = false
}

variable "log_retention_days" {
  type    = number
  default = 14
}
