terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state in S3 — Terraform backend blocks do not support variable
  # interpolation. Create this bucket manually before running terraform init,
  # then pass the name via: terraform init -backend-config="bucket=<your-bucket>"
  backend "s3" {
    bucket  = "REPLACE-WITH-YOUR-TF-STATE-BUCKET"
    key     = "devpulse/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
