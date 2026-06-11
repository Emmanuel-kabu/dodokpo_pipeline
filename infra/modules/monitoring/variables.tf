variable "name_prefix" {
  description = "Prefix applied to all monitoring resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "sync_lambda_name" {
  description = "Name of the Lambda function whose error metric the alarm watches."
  type        = string
}

variable "sfn_arn" {
  description = "ARN of the state machine whose execution-failure metric the alarm watches."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to the SNS alert topic. Subscription requires manual confirmation in AWS."
  type        = string
}
