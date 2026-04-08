output "ec2_public_ip" {
  description = "Public IP of the EC2 instance — set as API_BASE_URL in .env.prod"
  value       = aws_instance.app.public_ip
}

output "rds_endpoint" {
  description = "RDS PostgreSQL connection endpoint — use in DATABASE_URL"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "s3_bucket_name" {
  description = "S3 bucket name for PR diffs — set as S3_BUCKET_NAME in .env.prod"
  value       = aws_s3_bucket.artifacts.bucket
}

output "ecr_repository_url" {
  description = "ECR repository URL for the API image"
  value       = aws_ecr_repository.app.repository_url
}

output "cloudwatch_log_group_api" {
  description = "CloudWatch log group name for API logs"
  value       = aws_cloudwatch_log_group.api.name
}
