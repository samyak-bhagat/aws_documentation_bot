output "state_bucket_name" {
  description = "S3 bucket for Terraform remote state."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "lock_table_name" {
  description = "DynamoDB table for Terraform state locking."
  value       = aws_dynamodb_table.terraform_lock.name
}

output "aws_region" {
  description = "Region where bootstrap resources were created."
  value       = var.aws_region
}

output "aws_account_id" {
  description = "AWS account ID."
  value       = data.aws_caller_identity.current.account_id
}
