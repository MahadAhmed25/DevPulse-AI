terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 — create this bucket manually before first apply
  backend "s3" {
    bucket = "devpulse-terraform-state"
    key    = "devpulse/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "devpulse-ai"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
