variable "name_prefix" {
  description = "Prefix applied to all Lambda and ECR resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN of the Lambda execution role shared by all three functions."
  type        = string
}

variable "bronze_bucket_name" {
  description = "Name of the bronze S3 bucket; surfaced as BRONZE_BUCKET env var."
  type        = string
}

variable "silver_bucket_name" {
  description = "Name of the silver S3 bucket; surfaced as SILVER_BUCKET env var."
  type        = string
}

variable "gold_bucket_name" {
  description = "Name of the gold S3 bucket; surfaced as GOLD_BUCKET env var."
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of the Secrets Manager secret with RDS credentials; surfaced to the bronze sync as DB_SECRET_ARN."
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days for Lambda log groups."
  type        = number
  default     = 7
}

variable "lambda_timeout_seconds" {
  description = "Timeout (seconds) for each Lambda function."
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  description = "Memory (MB) allocation for each Lambda function."
  type        = number
  default     = 512
}

variable "image_tag_mutability" {
  description = "ECR image-tag mutability. IMMUTABLE prevents overwriting tags; pair with unique tags per build (commit SHA, semver)."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "image_tag" {
  description = "Initial ECR image tag baked into the Lambda function. CI updates the live tag out-of-band via API. The image must exist before first apply."
  type        = string
  default     = "bootstrap"
}

variable "ecr_keep_last_n_images" {
  description = "Number of most-recent tagged ECR images to retain per repository. Older tagged images are expired by the lifecycle policy."
  type        = number
  default     = 10

  validation {
    condition     = var.ecr_keep_last_n_images >= 1 && var.ecr_keep_last_n_images <= 1000
    error_message = "ecr_keep_last_n_images must be between 1 and 1000."
  }
}

variable "ecr_untagged_expire_days" {
  description = "Days to retain untagged ECR images (typically orphaned layers from rebuilds) before expiry."
  type        = number
  default     = 1

  validation {
    condition     = var.ecr_untagged_expire_days >= 1
    error_message = "ecr_untagged_expire_days must be at least 1."
  }
}
