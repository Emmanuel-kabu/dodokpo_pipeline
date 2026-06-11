locals {
  functions = {
    bronze = {
      suffix = "bronze-sync"
      env = {
        BRONZE_BUCKET = var.bronze_bucket_name
        DB_SECRET_ARN = var.db_secret_arn
        SSM_PREFIX    = "/${var.name_prefix}/watermarks"
      }
    }
    silver = {
      suffix = "silver-transform"
      env = {
        BRONZE_BUCKET = var.bronze_bucket_name
        SILVER_BUCKET = var.silver_bucket_name
      }
    }
    gold = {
      suffix = "gold-transform"
      env = {
        SILVER_BUCKET = var.silver_bucket_name
        GOLD_BUCKET   = var.gold_bucket_name
      }
    }
  }
}

resource "aws_ecr_repository" "this" {
  for_each             = local.functions
  name                 = "${var.name_prefix}-${each.value.suffix}"
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.ecr_untagged_expire_days} day(s)"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expire_days
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent ${var.ecr_keep_last_n_images} tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_keep_last_n_images
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = local.functions
  name              = "/aws/lambda/${var.name_prefix}-${each.value.suffix}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  for_each      = local.functions
  function_name = "${var.name_prefix}-${each.value.suffix}"
  role          = var.lambda_role_arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.this[each.key].repository_url}:${var.image_tag}"
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb

  environment {
    variables = each.value.env
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.this]
}
