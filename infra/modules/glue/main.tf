locals {
  layers = {
    bronze = {
      description = "Bronze layer — raw data synced from RDS"
      bucket      = var.bronze_bucket
      schedule    = var.bronze_schedule
    }
    silver = {
      description = "Silver layer — cleaned data"
      bucket      = var.silver_bucket
      schedule    = var.silver_schedule
    }
    gold = {
      description = "Gold layer — reshaped and business logic datasets"
      bucket      = var.gold_bucket
      schedule    = var.gold_schedule
    }
  }

  # Glue / Athena database names conventionally use underscores.
  db_prefix = replace(var.name_prefix, "-", "_")
}

resource "aws_glue_catalog_database" "this" {
  for_each    = local.layers
  name        = "${local.db_prefix}_${each.key}"
  description = each.value.description
}

# --- Crawler IAM ---

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "crawler" {
  name               = "${var.name_prefix}-glue-crawler-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.crawler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "crawler_s3" {
  statement {
    sid     = "ReadMedallionBuckets"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = flatten([
      for layer in local.layers : [
        "arn:aws:s3:::${layer.bucket}",
        "arn:aws:s3:::${layer.bucket}/*",
      ]
    ])
  }
}

resource "aws_iam_role_policy" "crawler_s3" {
  name   = "${var.name_prefix}-glue-s3-policy"
  role   = aws_iam_role.crawler.id
  policy = data.aws_iam_policy_document.crawler_s3.json
}

# --- Crawlers ---

# Bronze and gold: one crawler per layer scanning the whole bucket. Silver is
# split into per-source-database crawlers below so AssessmentTaker (which
# appears in both source DBs) doesn't collide on table name.
resource "aws_glue_crawler" "this" {
  for_each      = { for k, v in local.layers : k => v if k != "silver" }
  name          = "${var.name_prefix}-${each.key}-crawler"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this[each.key].name
  schedule      = each.value.schedule

  s3_target {
    path = "s3://${each.value.bucket}/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })
}

# Silver: one crawler per source database, each writing into the silver Glue
# database with a table-name prefix derived from the source DB. Resulting
# tables look like `test_creation_assessment`, `test_execution_testresult`.
locals {
  silver_sources = {
    test_creation  = "dodokpo_test_creation_staging"
    test_execution = "dodokpo_test_execution_staging"
    user_mgt       = "dodokpo_user_mgt_staging"
  }
}

resource "aws_glue_crawler" "silver" {
  for_each      = local.silver_sources
  name          = "${var.name_prefix}-silver-${each.key}-crawler"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this["silver"].name
  schedule      = var.silver_schedule
  table_prefix  = "${each.key}_"

  s3_target {
    path = "s3://${var.silver_bucket}/${each.value}/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })
}
