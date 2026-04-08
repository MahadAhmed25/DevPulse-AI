# DevPulse AI — Terraform Infrastructure

All AWS infrastructure for DevPulse, managed with Terraform.
Written during Phase 0.5 — **not applied until Phase 7 (deployment)**.

## Architecture

```
Internet → EC2 t2.micro (public subnet 10.0.1.0/24)
                ↓
           RDS db.t3.micro (private subnet 10.0.2.0/24 + 10.0.3.0/24)

EC2 IAM role → S3 (diffs), Bedrock (embeddings), CloudWatch (logs)
Redis → Redis Cloud free tier (external, no ElastiCache)
```

## Files

| File | What it creates |
|---|---|
| `main.tf` | Terraform settings, AWS + random providers, S3 backend |
| `variables.tf` | All input variables with descriptions |
| `vpc.tf` | VPC (10.0.0.0/16), public subnet, 2× private subnets, IGW, route table |
| `ec2.tf` | Security group, AMI data source, EC2 t2.micro instance |
| `iam.tf` | EC2 IAM role, inline policy (S3/Bedrock/CloudWatch), instance profile |
| `rds.tf` | RDS security group, DB subnet group, PostgreSQL 16.3 instance |
| `s3.tf` | S3 bucket with random suffix, AES256 encryption, 90-day lifecycle |
| `ecr.tf` | ECR repositories for api + worker, lifecycle policy (keep last 10) |
| `cloudwatch.tf` | Log groups (/devpulse/api, /devpulse/worker), SNS topic, CPU alarm |
| `outputs.tf` | ec2_public_ip, rds_endpoint, s3_bucket_name, ecr_repository_url, cloudwatch_log_group_api |
| `redis_note.md` | Why we use Redis Cloud instead of ElastiCache |

## Prerequisites

Before running Terraform you need:

1. **AWS CLI configured** — `aws configure` with an IAM user that has admin permissions
2. **S3 bucket for state** — create manually:
   ```bash
   aws s3 mb s3://YOUR-TF-STATE-BUCKET --region us-east-1
   aws s3api put-bucket-versioning \
     --bucket YOUR-TF-STATE-BUCKET \
     --versioning-configuration Status=Enabled
   ```
3. **EC2 key pair** — create in AWS Console or:
   ```bash
   aws ec2 create-key-pair --key-name devpulse-key \
     --query 'KeyMaterial' --output text > ~/.ssh/devpulse-key.pem
   chmod 400 ~/.ssh/devpulse-key.pem
   ```
4. **Your IP** — find it: `curl ifconfig.me`

## terraform.tfvars

Create `infra/terraform.tfvars` (gitignored — never commit this):

```hcl
tf_state_bucket   = "your-tf-state-bucket-name"
db_password       = "a-strong-random-password"
ec2_key_pair_name = "devpulse-key"
your_ip_cidr      = "YOUR.IP.ADDRESS/32"
```

## How to Apply

```bash
cd infra

# 1. Initialise — downloads providers, connects to S3 backend
terraform init -backend-config="bucket=YOUR-TF-STATE-BUCKET"

# 2. Preview what will be created
terraform plan -var-file="terraform.tfvars"

# 3. Apply (creates all AWS resources — ~2 minutes)
terraform apply -var-file="terraform.tfvars"

# 4. Copy outputs into .env.prod
terraform output ec2_public_ip
terraform output -raw s3_bucket_name
terraform output -raw ecr_repository_url
```

## How to Destroy

```bash
terraform destroy -var-file="terraform.tfvars"
```

> **Warning:** This deletes all resources including the RDS database.
> The RDS instance has `skip_final_snapshot = true` for dev/demo — no snapshot is taken.

## Estimated Monthly Cost (after AWS Free Tier expires)

| Resource | Cost |
|---|---|
| EC2 t2.micro | ~$0 (free tier 12 months) / ~$8.50 after |
| RDS db.t3.micro | ~$15/month |
| S3 (diffs storage) | ~$1/month |
| ECR (image storage) | ~$1/month |
| CloudWatch logs | ~$0.50/month |
| Redis Cloud free tier | $0 |
| **Total** | **~$17–20/month** (after free tier) |

During free tier (first 12 months): ~$2–3/month.
