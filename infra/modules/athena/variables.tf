variable "name_prefix" {
  description = "Prefix applied to all Athena resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "results_bucket" {
  description = "Name of the S3 bucket that holds Athena query results."
  type        = string
}

variable "gold_database" {
  description = "Name of the gold Glue catalog database."
  type        = string
}
