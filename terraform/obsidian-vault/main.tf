terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- S3 Bucket ---

resource "aws_s3_bucket" "obsidian_vault" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "obsidian_vault" {
  bucket = aws_s3_bucket.obsidian_vault.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "obsidian_vault" {
  bucket = aws_s3_bucket.obsidian_vault.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "obsidian_vault" {
  bucket = aws_s3_bucket.obsidian_vault.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "obsidian_vault" {
  bucket = aws_s3_bucket.obsidian_vault.id

  rule {
    id     = "cleanup-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }
  }
}

# --- IAM User for Pi Agent ---

resource "aws_iam_user" "vault_agent" {
  name = "obsidian-vault-agent"
}

resource "aws_iam_access_key" "vault_agent" {
  user = aws_iam_user.vault_agent.name
}

resource "aws_iam_user_policy" "vault_agent" {
  name = "obsidian-vault-access"
  user = aws_iam_user.vault_agent.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.obsidian_vault.arn,
          "${aws_s3_bucket.obsidian_vault.arn}/*",
        ]
      }
    ]
  })
}
