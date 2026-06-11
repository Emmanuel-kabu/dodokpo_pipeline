locals {
  name_prefix = "${var.project}-${var.environment}"
}

module "iam" {
  source                  = "./modules/iam"
  name_prefix             = local.name_prefix
  db_secret_arn           = var.db_secret_arn
  rds_export_kms_key_arns = var.rds_export_kms_key_arns
}

module "s3" {
  source               = "./modules/s3"
  name_prefix          = local.name_prefix
  rds_export_role_arns = var.rds_export_role_arns
}

module "glue" {
  source          = "./modules/glue"
  name_prefix     = local.name_prefix
  bronze_bucket   = module.s3.bronze_bucket_name
  silver_bucket   = module.s3.silver_bucket_name
  gold_bucket     = module.s3.gold_bucket_name
  bronze_schedule = var.glue_bronze_schedule
  silver_schedule = var.glue_silver_schedule
  gold_schedule   = var.glue_gold_schedule
}

module "athena" {
  source         = "./modules/athena"
  name_prefix    = local.name_prefix
  results_bucket = module.s3.athena_results_bucket_name
  gold_database  = module.glue.gold_database_name
}

module "lambda" {
  source             = "./modules/lambda"
  name_prefix        = local.name_prefix
  lambda_role_arn    = module.iam.lambda_role_arn
  bronze_bucket_name = module.s3.bronze_bucket_name
  silver_bucket_name = module.s3.silver_bucket_name
  gold_bucket_name   = module.s3.gold_bucket_name
  db_secret_arn      = var.db_secret_arn
  log_retention_days = var.log_retention_days
}

module "step_functions" {
  source             = "./modules/step_functions"
  name_prefix        = local.name_prefix
  sfn_role_arn       = module.iam.sfn_role_arn
  silver_lambda_arn  = module.lambda.silver_lambda_arn
  gold_lambda_arn    = module.lambda.gold_lambda_arn
  gold_datasets      = var.gold_datasets
  log_retention_days = var.log_retention_days
  log_level          = var.sfn_log_level
}

module "eventbridge" {
  source        = "./modules/eventbridge"
  name_prefix   = local.name_prefix
  sfn_arn       = module.step_functions.sfn_arn
  sfn_role_arn  = module.iam.eventbridge_sfn_role_arn
  schedule      = var.sync_schedule
  silver_tables = var.silver_tables
  gold_datasets = var.gold_datasets
}

module "monitoring" {
  source           = "./modules/monitoring"
  name_prefix      = local.name_prefix
  sync_lambda_name = module.lambda.bronze_lambda_name
  sfn_arn          = module.step_functions.sfn_arn
  alert_email      = var.alert_email
}
