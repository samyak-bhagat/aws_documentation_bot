output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "api_service_name" {
  value = aws_ecs_service.api.name
}

output "ui_service_name" {
  value = aws_ecs_service.ui.name
}
