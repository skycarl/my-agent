variable "bucket_name" {
  description = "Name of the S3 bucket for the Obsidian vault"
  type        = string
  default     = "my-obsidian-vault"
}

variable "aws_region" {
  description = "AWS region for the S3 bucket"
  type        = string
  default     = "us-west-2"
}

variable "noncurrent_version_retention_days" {
  description = "Days to keep non-current object versions before deletion"
  type        = number
  default     = 30
}
