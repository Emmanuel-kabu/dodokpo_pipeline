output "lambda_role_arn" {
  description = "ARN of the Lambda execution role shared by the three medallion functions."
  value       = aws_iam_role.lambda.arn
}

output "sfn_role_arn" {
  description = "ARN of the Step Functions state-machine role."
  value       = aws_iam_role.sfn.arn
}

output "eventbridge_sfn_role_arn" {
  description = "ARN of the EventBridge Scheduler role that starts the state machine."
  value       = aws_iam_role.eventbridge_sfn.arn
}
