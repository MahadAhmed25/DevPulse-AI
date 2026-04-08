variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Deployment environment (production | staging)"
}

variable "project_name" {
  type        = string
  default     = "devpulse"
  description = "Project name prefix used in resource names"
}

variable "tf_state_bucket" {
  type        = string
  description = "S3 bucket name for Terraform remote state (create manually before terraform init)"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Master password for the RDS PostgreSQL instance"
}

variable "ec2_key_pair_name" {
  type        = string
  description = "Name of an existing EC2 key pair for SSH access"
}

variable "your_ip_cidr" {
  type        = string
  description = "Your IP address in CIDR notation for SSH access (e.g. 203.0.113.1/32)"
}
