terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.94"
    }
  }

  # Backend must be configured before first apply to keep state remote and encrypted.
  # Uses S3 native locking (use_lockfile) — no DynamoDB table required.
  # Bucket must be created out-of-band before `terraform init`.
  backend "s3" {
    bucket       = "dodokpo-tf-state-v1"
    key          = "dodokpo/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
