output "bronze_lambda_arn" {
  description = "ARN of the bronze sync Lambda function."
  value       = aws_lambda_function.this["bronze"].arn
}

output "bronze_lambda_name" {
  description = "Name of the bronze sync Lambda function."
  value       = aws_lambda_function.this["bronze"].function_name
}

output "silver_lambda_arn" {
  description = "ARN of the silver transform Lambda function."
  value       = aws_lambda_function.this["silver"].arn
}

output "silver_lambda_name" {
  description = "Name of the silver transform Lambda function."
  value       = aws_lambda_function.this["silver"].function_name
}

output "gold_lambda_arn" {
  description = "ARN of the gold transform Lambda function."
  value       = aws_lambda_function.this["gold"].arn
}

output "gold_lambda_name" {
  description = "Name of the gold transform Lambda function."
  value       = aws_lambda_function.this["gold"].function_name
}

output "bronze_ecr_url" {
  description = "ECR repository URL for the bronze sync image."
  value       = aws_ecr_repository.this["bronze"].repository_url
}

output "silver_ecr_url" {
  description = "ECR repository URL for the silver transform image."
  value       = aws_ecr_repository.this["silver"].repository_url
}

output "gold_ecr_url" {
  description = "ECR repository URL for the gold transform image."
  value       = aws_ecr_repository.this["gold"].repository_url
}
