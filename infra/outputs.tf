output "ec2_public_ip" {
  description = "Public IP of the EC2 instance (webhook + API endpoint)"
  value       = aws_instance.app.public_ip
}

output "rds_endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repository URL for the API image"
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_worker_repository_url" {
  description = "ECR repository URL for the worker image"
  value       = aws_ecr_repository.worker.repository_url
}

output "s3_bucket_name" {
  description = "S3 bucket used for PR diffs and artifacts"
  value       = aws_s3_bucket.artifacts.bucket
}
