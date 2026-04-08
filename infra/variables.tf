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

variable "project" {
  type        = string
  default     = "devpulse"
  description = "Project name prefix used in resource names"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "ec2_instance_type" {
  type    = string
  default = "t3.small"
}

variable "ec2_key_name" {
  type        = string
  description = "Name of an existing EC2 key pair for SSH access"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "rds_username" {
  type      = string
  sensitive = true
}

variable "rds_password" {
  type      = string
  sensitive = true
}

variable "rds_database_name" {
  type    = string
  default = "devpulse"
}

variable "elasticache_node_type" {
  type    = string
  default = "cache.t3.micro"
}

variable "s3_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for PR diffs and artifacts"
}
