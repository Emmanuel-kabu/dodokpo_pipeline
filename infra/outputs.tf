output "bronze_bucket_name" {
  description = "Name of the bronze layer S3 bucket."
  value       = module.s3.bronze_bucket_name
}

output "bronze_bucket_arn" {
  description = "ARN of the bronze layer S3 bucket. Share with the prod DB team so they can target it from RDS Export to S3."
  value       = module.s3.bronze_bucket_arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role. Share with the prod DB team if they need to grant cross-account KMS Decrypt for export reads."
  value       = module.iam.lambda_role_arn
}

output "silver_bucket_name" {
  description = "Name of the silver layer S3 bucket."
  value       = module.s3.silver_bucket_name
}

output "gold_bucket_name" {
  description = "Name of the gold layer S3 bucket."
  value       = module.s3.gold_bucket_name
}

output "athena_results_bucket_name" {
  description = "Name of the bucket holding Athena query results (30-day TTL)."
  value       = module.s3.athena_results_bucket_name
}

output "glue_bronze_database" {
  description = "Name of the Glue catalog database for the bronze layer."
  value       = module.glue.bronze_database_name
}

output "glue_silver_database" {
  description = "Name of the Glue catalog database for the silver layer."
  value       = module.glue.silver_database_name
}

output "glue_gold_database" {
  description = "Name of the Glue catalog database for the gold layer."
  value       = module.glue.gold_database_name
}

output "athena_workgroup_name" {
  description = "Athena workgroup used for ad-hoc and downstream queries."
  value       = module.athena.workgroup_name
}

output "bronze_lambda_arn" {
  description = "ARN of the bronze sync Lambda function."
  value       = module.lambda.bronze_lambda_arn
}

output "silver_lambda_arn" {
  description = "ARN of the silver transform Lambda function."
  value       = module.lambda.silver_lambda_arn
}

output "gold_lambda_arn" {
  description = "ARN of the gold transform Lambda function."
  value       = module.lambda.gold_lambda_arn
}

output "bronze_ecr_url" {
  description = "ECR repository URL for the bronze sync Lambda image."
  value       = module.lambda.bronze_ecr_url
}

output "silver_ecr_url" {
  description = "ECR repository URL for the silver transform Lambda image."
  value       = module.lambda.silver_ecr_url
}

output "gold_ecr_url" {
  description = "ECR repository URL for the gold transform Lambda image."
  value       = module.lambda.gold_ecr_url
}

output "sfn_arn" {
  description = "ARN of the medallion pipeline Step Functions state machine."
  value       = module.step_functions.sfn_arn
}

output "sns_alert_topic_arn" {
  description = "ARN of the SNS topic for failure alerts."
  value       = module.monitoring.sns_topic_arn
}
