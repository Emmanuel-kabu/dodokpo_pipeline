variable "name_prefix" {
  description = "Prefix applied to all Glue resources; typically \"<project>-<environment>\"."
  type        = string
}

variable "bronze_bucket" {
  description = "Name of the bronze S3 bucket crawled by the bronze crawler."
  type        = string
}

variable "silver_bucket" {
  description = "Name of the silver S3 bucket crawled by the silver crawler."
  type        = string
}

variable "gold_bucket" {
  description = "Name of the gold S3 bucket crawled by the gold crawler."
  type        = string
}

variable "bronze_schedule" {
  description = "Cron schedule for the bronze Glue crawler."
  type        = string
  default     = "cron(30 2 * * ? *)"
}

variable "silver_schedule" {
  description = "Cron schedule for the silver Glue crawler."
  type        = string
  default     = "cron(30 3 * * ? *)"
}

variable "gold_schedule" {
  description = "Cron schedule for the gold Glue crawler."
  type        = string
  default     = "cron(30 4 * * ? *)"
}
