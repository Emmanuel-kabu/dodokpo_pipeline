resource "aws_scheduler_schedule" "sync" {
  name       = "${var.name_prefix}-incremental-sync"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = var.schedule

  target {
    arn      = var.sfn_arn
    role_arn = var.sfn_role_arn

    input = jsonencode({
      tables   = var.silver_tables
      datasets = var.gold_datasets
    })
  }
}
