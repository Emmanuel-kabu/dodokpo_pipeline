output "sfn_arn" {
  description = "ARN of the medallion pipeline state machine."
  value       = aws_sfn_state_machine.pipeline.arn
}

output "sfn_name" {
  description = "Name of the medallion pipeline state machine."
  value       = aws_sfn_state_machine.pipeline.name
}
