data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# --- Assume-role trust documents ---

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eventbridge_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

# --- Lambda execution role ---

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid     = "MedallionBuckets"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${var.name_prefix}-bronze",
      "arn:aws:s3:::${var.name_prefix}-bronze/*",
      "arn:aws:s3:::${var.name_prefix}-silver",
      "arn:aws:s3:::${var.name_prefix}-silver/*",
      "arn:aws:s3:::${var.name_prefix}-gold",
      "arn:aws:s3:::${var.name_prefix}-gold/*",
    ]
  }

  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }

  statement {
    sid     = "Watermarks"
    actions = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/*",
    ]
  }

  statement {
    sid     = "Logging"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*",
    ]
  }

  # ecr:GetAuthorizationToken does not support resource-level permissions; it must use "*".
  statement {
    sid       = "EcrAuthToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/${var.name_prefix}-*",
    ]
  }

  # Decrypt RDS exports written with a cross-account KMS key (prod DB team owns the key).
  dynamic "statement" {
    for_each = length(var.rds_export_kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptRdsExports"
      actions   = ["kms:Decrypt", "kms:DescribeKey"]
      resources = var.rds_export_kms_key_arns
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name_prefix}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# --- Step Functions role ---

resource "aws_iam_role" "sfn" {
  name               = "${var.name_prefix}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid     = "InvokePipelineLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.name_prefix}-*",
    ]
  }

  # CloudWatch log-delivery API actions do not support resource-level permissions.
  statement {
    sid = "LogDelivery"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${var.name_prefix}-sfn-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

# --- EventBridge Scheduler role ---

resource "aws_iam_role" "eventbridge_sfn" {
  name               = "${var.name_prefix}-eventbridge-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume.json
}

data "aws_iam_policy_document" "eventbridge_sfn" {
  statement {
    sid     = "StartPipelineExecution"
    actions = ["states:StartExecution"]
    resources = [
      "arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.name_prefix}-*",
    ]
  }
}

resource "aws_iam_role_policy" "eventbridge_sfn" {
  name   = "${var.name_prefix}-eventbridge-sfn-policy"
  role   = aws_iam_role.eventbridge_sfn.id
  policy = data.aws_iam_policy_document.eventbridge_sfn.json
}
