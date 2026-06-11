resource "aws_athena_workgroup" "main" {
  name = "${var.name_prefix}-workgroup"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 GB safety limit

    result_configuration {
      output_location = "s3://${var.results_bucket}/query-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_athena_named_query" "trainer_metrics" {
  name      = "${var.name_prefix}-trainer-metrics-views"
  workgroup = aws_athena_workgroup.main.id
  database  = var.gold_database
  query     = file("${path.module}/../../sql/trainer_executive_metrics_views.sql")
}
