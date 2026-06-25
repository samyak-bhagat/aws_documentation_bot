output "ecs_task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  value = aws_iam_role.ecs_task.arn
}

output "ecs_task_role_name" {
  value = aws_iam_role.ecs_task.name
}

output "github_actions_role_arn" {
  value = var.enable_github_oidc ? aws_iam_role.github_actions[0].arn : null
}
