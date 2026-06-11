locals {
  buckets = {
    bronze         = { versioning = true, expire_days = null }
    silver         = { versioning = true, expire_days = null }
    gold           = { versioning = true, expire_days = null }
    athena-results = { versioning = false, expire_days = 30 }
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  bucket   = "${var.name_prefix}-${each.key}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = { for k, v in local.buckets : k => v if v.versioning }
  bucket   = aws_s3_bucket.this[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = { for k, v in local.buckets : k => v if v.expire_days != null }
  bucket   = aws_s3_bucket.this[each.key].id

  rule {
    id     = "expire-objects"
    status = "Enabled"

    filter {}

    expiration {
      days = each.value.expire_days
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "bucket" {
  for_each = aws_s3_bucket.this

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      each.value.arn,
      "${each.value.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Bronze bucket only: allow the production account's RDS Export role(s) to write.
  dynamic "statement" {
    for_each = (each.key == "bronze" && length(var.rds_export_role_arns) > 0) ? [1] : []

    content {
      sid    = "AllowRdsExportWrite"
      effect = "Allow"
      actions = [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts",
      ]
      resources = [
        each.value.arn,
        "${each.value.arn}/*",
      ]
      principals {
        type        = "AWS"
        identifiers = var.rds_export_role_arns
      }
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  policy   = data.aws_iam_policy_document.bucket[each.key].json
}
