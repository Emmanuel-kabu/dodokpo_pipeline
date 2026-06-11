resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/states/${var.name_prefix}-medallion-pipeline"
  retention_in_days = var.log_retention_days
}

# Silver then gold pipeline. Bronze is still produced out-of-band by the
# platform engineer's RDS export job, so this state machine starts at the
# silver transform and then runs the gold transform over the cleaned silver
# outputs.
resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.name_prefix}-medallion-pipeline"
  role_arn = var.sfn_role_arn

  definition = jsonencode({
    Comment = "Silver and gold pipeline: clean bronze extracts into silver, then derive gold KPIs."
    StartAt = "SilverTransform"
    States = {
      SilverTransform = {
        Type           = "Map"
        ItemsPath      = "$.tables"
        ResultPath     = "$.silver_results"
        Next           = "InjectGoldDatasets"
        MaxConcurrency = 10
        Iterator = {
          StartAt = "CleanTable"
          States = {
            CleanTable = {
              Type     = "Task"
              Resource = var.silver_lambda_arn
              Retry = [{
                ErrorEquals     = ["States.TaskFailed"]
                IntervalSeconds = 30
                MaxAttempts     = 3
                BackoffRate     = 2
              }]
              End = true
            }
          }
        }
      }
      InjectGoldDatasets = {
        Type       = "Pass"
        Result     = var.gold_datasets
        ResultPath = "$.datasets"
        Next       = "GoldTransform"
      }
      GoldTransform = {
        Type           = "Map"
        ItemsPath      = "$.datasets"
        MaxConcurrency = 5
        Iterator = {
          StartAt = "BuildGoldDataset"
          States = {
            BuildGoldDataset = {
              Type     = "Task"
              Resource = var.gold_lambda_arn
              Parameters = {
                "dataset.$" : "$"
              }
              Retry = [{
                ErrorEquals     = ["States.TaskFailed"]
                IntervalSeconds = 30
                MaxAttempts     = 3
                BackoffRate     = 2
              }]
              End = true
            }
          }
        }
        End = true
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.pipeline.arn}:*"
    include_execution_data = false
    level                  = var.log_level
  }
}
