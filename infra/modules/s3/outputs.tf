output "bronze_bucket_name" {
  description = "Name of the bronze layer S3 bucket."
  value       = aws_s3_bucket.this["bronze"].bucket
}

output "silver_bucket_name" {
  description = "Name of the silver layer S3 bucket."
  value       = aws_s3_bucket.this["silver"].bucket
}

output "gold_bucket_name" {
  description = "Name of the gold layer S3 bucket."
  value       = aws_s3_bucket.this["gold"].bucket
}

output "athena_results_bucket_name" {
  description = "Name of the Athena query results S3 bucket."
  value       = aws_s3_bucket.this["athena-results"].bucket
}

output "bronze_bucket_arn" {
  description = "ARN of the bronze layer S3 bucket."
  value       = aws_s3_bucket.this["bronze"].arn
}

output "silver_bucket_arn" {
  description = "ARN of the silver layer S3 bucket."
  value       = aws_s3_bucket.this["silver"].arn
}

output "gold_bucket_arn" {
  description = "ARN of the gold layer S3 bucket."
  value       = aws_s3_bucket.this["gold"].arn
}

output "athena_results_bucket_arn" {
  description = "ARN of the Athena query results S3 bucket."
  value       = aws_s3_bucket.this["athena-results"].arn
}
