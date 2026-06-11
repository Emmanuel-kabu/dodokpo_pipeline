variable "name_prefix" {
  description = "Prefix applied to all scheduler resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "sfn_arn" {
  description = "ARN of the state machine targeted by the schedule."
  type        = string
}

variable "sfn_role_arn" {
  description = "ARN of the IAM role used by EventBridge Scheduler to start the state machine."
  type        = string
}

variable "schedule" {
  description = "Cron or rate expression for the recurring trigger."
  type        = string
}

variable "silver_tables" {
  description = "List of {database, table} objects passed to the Step Functions Map state. One silver Lambda invocation per entry."
  type = list(object({
    database = string
    table    = string
  }))
}

variable "gold_datasets" {
  description = "List of gold dataset names passed to the Step Functions pipeline after silver completes."
  type        = list(string)
}
