variable "name_prefix" {
  description = "Prefix applied to all IAM resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of the Secrets Manager secret with RDS credentials granted to the Lambda role."
  type        = string
  sensitive   = true
}

variable "rds_export_kms_key_arns" {
  description = "ARNs of cross-account KMS keys used by the production account to encrypt RDS exports. The lambda role gets kms:Decrypt on these so it can read exported Parquet. Empty list = no KMS grant added."
  type        = list(string)
  default     = []
}
