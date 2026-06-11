output "bronze_database_name" {
  description = "Name of the bronze Glue catalog database."
  value       = aws_glue_catalog_database.this["bronze"].name
}

output "silver_database_name" {
  description = "Name of the silver Glue catalog database."
  value       = aws_glue_catalog_database.this["silver"].name
}

output "gold_database_name" {
  description = "Name of the gold Glue catalog database."
  value       = aws_glue_catalog_database.this["gold"].name
}

output "bronze_crawler_name" {
  description = "Name of the bronze Glue crawler."
  value       = aws_glue_crawler.this["bronze"].name
}

output "silver_crawler_names" {
  description = "Names of the per-source-database silver Glue crawlers."
  value       = { for k, v in aws_glue_crawler.silver : k => v.name }
}

output "gold_crawler_name" {
  description = "Name of the gold Glue crawler."
  value       = aws_glue_crawler.this["gold"].name
}
