output "schedule_arn" {
  description = "ARN of the EventBridge schedule that triggers the state machine."
  value       = aws_scheduler_schedule.sync.arn
}
