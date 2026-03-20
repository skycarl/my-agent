output "bucket_name" {
  description = "Name of the Obsidian vault S3 bucket"
  value       = aws_s3_bucket.obsidian_vault.id
}

output "bucket_arn" {
  description = "ARN of the Obsidian vault S3 bucket"
  value       = aws_s3_bucket.obsidian_vault.arn
}

output "access_key_id" {
  description = "Access key ID for the vault agent IAM user"
  value       = aws_iam_access_key.vault_agent.id
  sensitive   = true
}

output "secret_access_key" {
  description = "Secret access key for the vault agent IAM user"
  value       = aws_iam_access_key.vault_agent.secret
  sensitive   = true
}
