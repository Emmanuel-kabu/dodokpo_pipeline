variable "name_prefix" {
  description = "Prefix applied to all Step Functions resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "sfn_role_arn" {
  description = "ARN of the IAM role assumed by the state machine."
  type        = string
}

variable "silver_lambda_arn" {
  description = "ARN of the silver transform Lambda invoked in the SilverTransform map state."
  type        = string
}

variable "gold_lambda_arn" {
  description = "ARN of the gold transform Lambda invoked after silver completes."
  type        = string
}

variable "gold_datasets" {
  description = "List of gold dataset names passed to the gold transform map state."
  type        = list(string)
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days for the state-machine log group."
  type        = number
  default     = 7
}

variable "log_level" {
  description = "Step Functions execution log level. Use ALL for non-prod debugging, ERROR for prod."
  type        = string
  default     = "ERROR"

  validation {
    condition     = contains(["ALL", "ERROR", "FATAL", "OFF"], var.log_level)
    error_message = "log_level must be one of: ALL, ERROR, FATAL, OFF."
  }
}
