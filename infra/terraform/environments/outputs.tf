output "vpc_id" {
  value = module.vpc.vpc_id
}

output "alb_dns_name" {
  description = "Application URL (HTTP). Open in browser after first image push."
  value       = "http://${module.alb.alb_dns_name}"
}

output "ecr_api_repository_url" {
  value = module.ecr.api_repository_url
}

output "ecr_ui_repository_url" {
  value = module.ecr.ui_repository_url
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "opensearch_endpoint" {
  value = module.opensearch.endpoint
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "github_actions_role_arn" {
  value = module.iam.github_actions_role_arn
}

output "aws_account_id" {
  value = local.account_id
}

output "aws_region" {
  value = var.aws_region
}
