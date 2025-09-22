output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.multi_tenant_pool.id
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.multi_tenant_client.id
}

output "sessions_table_name" {
  description = "DynamoDB Sessions Table Name"
  value       = aws_dynamodb_table.tenant_sessions.name
}

output "usage_table_name" {
  description = "DynamoDB Usage Table Name"
  value       = aws_dynamodb_table.tenant_usage.name
}

output "app_role_arn" {
  description = "Application IAM Role ARN"
  value       = aws_iam_role.app_role.arn
}