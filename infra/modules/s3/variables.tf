variable "name_prefix" {
  description = "Prefix applied to all bucket names; typically \"<project>-<environment>\"."
  type        = string
}

variable "rds_export_role_arns" {
  description = "ARNs of cross-account IAM roles allowed to write RDS Export output into the bronze bucket. Empty list = no cross-account write allowed."
  type        = list(string)
  default     = []
}
