variable "project" {
  description = "Project name used as a prefix for all resources."
  type        = string
  default     = "dodokpo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.project))
    error_message = "project must be lowercase alphanumeric with hyphens, 3-32 chars, not starting or ending with a hyphen."
  }
}

variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region to deploy resources."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-\\d+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region identifier (e.g. eu-west-1)."
  }
}

variable "db_secret_arn" {
  description = "ARN of the Secrets Manager secret containing RDS credentials."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^arn:aws:secretsmanager:[a-z0-9-]+:\\d{12}:secret:.+$", var.db_secret_arn))
    error_message = "db_secret_arn must be a valid Secrets Manager ARN."
  }
}

variable "sync_schedule" {
  description = "EventBridge cron schedule for incremental sync. Default runs twice daily at 02:00 and 14:00 UTC."
  type        = string
  default     = "cron(0 2,14 * * ? *)"
}

variable "alert_email" {
  description = "Email address subscribed to the SNS alerts topic. Subscription requires manual confirmation in AWS."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be a valid email address."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days. Must be a CloudWatch-allowed value."
  type        = number
  default     = 7

  validation {
    condition = contains(
      [0, 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 2192, 2557, 2922, 3288, 3653],
      var.log_retention_days
    )
    error_message = "log_retention_days must be a valid CloudWatch retention period."
  }
}

variable "tables_to_sync" {
  description = "List of source RDS table names handed to the bronze sync Lambda by the schedule trigger."
  type        = list(string)
  default = [
    "assessment",
    "assessment_taker",
    "test",
    "question",
    "skill",
    "skill_level",
    "skill_level_assignment",
    "test_result",
    "draft",
    "identity",
    "window_violation",
    "question_flag",
  ]
}

variable "gold_datasets" {
  description = "List of gold dataset names handed to the gold transform Lambda by the schedule trigger."
  type        = list(string)
  default = [
    "test_creation_category",
    "test_creation_assessment_taker",
    "test_creation_domain",
    "test_execution_questionflag",
    "test_execution_testresult",
    "test_creation_test",
    "test_creation_question",
    "test_creation_assessment",
    "test_creation_skill",
    "test_creation_assessment_dispatch",
  ]
}

variable "silver_tables" {
  description = "Tables to process from bronze to silver. Each entry triggers one silver Lambda invocation in the Step Functions Map state."
  type = list(object({
    database = string
    table    = string
  }))
  default = [
    # test_creation
    { database = "dodokpo_test_creation_staging", table = "Assessment" },
    { database = "dodokpo_test_creation_staging", table = "AssessmentDispatch" },
    { database = "dodokpo_test_creation_staging", table = "AssessmentTaker" },
    { database = "dodokpo_test_creation_staging", table = "Category" },
    { database = "dodokpo_test_creation_staging", table = "Code" },
    { database = "dodokpo_test_creation_staging", table = "Domain" },
    { database = "dodokpo_test_creation_staging", table = "Question" },
    { database = "dodokpo_test_creation_staging", table = "QuestionVersion" },
    { database = "dodokpo_test_creation_staging", table = "Skill" },
    { database = "dodokpo_test_creation_staging", table = "SkillLevel" },
    { database = "dodokpo_test_creation_staging", table = "SkillLevelAssignment" },
    { database = "dodokpo_test_creation_staging", table = "Test" },
    { database = "dodokpo_test_creation_staging", table = "TestQuestion" },
    { database = "dodokpo_test_creation_staging", table = "_SkillToSkillLevel" },
    { database = "dodokpo_test_creation_staging", table = "_TestsToAssessments" },
    # test_execution
    { database = "dodokpo_test_execution_staging", table = "AssessmentTakingLog" },
    { database = "dodokpo_test_execution_staging", table = "AssessmentTaker" },
    { database = "dodokpo_test_execution_staging", table = "Identity" },
    { database = "dodokpo_test_execution_staging", table = "QuestionFlag" },
    { database = "dodokpo_test_execution_staging", table = "ScreenShot" },
    { database = "dodokpo_test_execution_staging", table = "TestResult" },
    { database = "dodokpo_test_execution_staging", table = "WindowViolation" },
    # user_mgt — organization name lookup for org-level slicing
    { database = "dodokpo_user_mgt_staging", table = "organizations" },
  ]
}

variable "glue_bronze_schedule" {
  description = "Cron schedule for the bronze Glue crawler."
  type        = string
  default     = "cron(30 2 * * ? *)"
}

variable "glue_silver_schedule" {
  description = "Cron schedule for the silver Glue crawler."
  type        = string
  default     = "cron(30 3 * * ? *)"
}

variable "glue_gold_schedule" {
  description = "Cron schedule for the gold Glue crawler."
  type        = string
  default     = "cron(30 4 * * ? *)"
}

variable "rds_export_role_arns" {
  description = "ARNs of IAM roles in the production AWS account that perform RDS Export to S3 into the bronze bucket. The bronze bucket policy grants these roles s3:PutObject and related actions. Leave empty until the prod team shares the role ARN(s)."
  type        = list(string)
  default     = []
}

variable "rds_export_kms_key_arns" {
  description = "ARNs of cross-account KMS keys used by the production account to encrypt RDS exports. The bronze Lambda role is granted kms:Decrypt on these keys so it can read the exported Parquet. Leave empty until the prod team shares the key ARN(s)."
  type        = list(string)
  default     = []
}

variable "sfn_log_level" {
  description = "Step Functions execution log level. Use ALL for non-prod debugging, ERROR for prod."
  type        = string
  default     = "ERROR"

  validation {
    condition     = contains(["ALL", "ERROR", "FATAL", "OFF"], var.sfn_log_level)
    error_message = "sfn_log_level must be one of: ALL, ERROR, FATAL, OFF."
  }
}
