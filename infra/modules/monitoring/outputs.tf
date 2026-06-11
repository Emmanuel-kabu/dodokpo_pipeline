output "sns_topic_arn" {
  description = "ARN of the SNS topic that receives failure alerts."
  value       = aws_sns_topic.alerts.arn
}
