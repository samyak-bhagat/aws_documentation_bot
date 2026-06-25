output "api_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ui_repository_url" {
  value = aws_ecr_repository.ui.repository_url
}

output "api_repository_arn" {
  value = aws_ecr_repository.api.arn
}

output "ui_repository_arn" {
  value = aws_ecr_repository.ui.arn
}
