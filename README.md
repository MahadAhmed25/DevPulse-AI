# DevPulse AI

AI-powered code review on GitHub pull requests using RAG over your codebase.

## Stack

- **Backend**: Python 3.11 + FastAPI + Celery
- **Database**: AWS RDS PostgreSQL 16 + pgvector
- **Embeddings**: Amazon Bedrock (Titan Embeddings V2)
- **LLM**: Anthropic Claude (Haiku for speed, Sonnet for deep reviews)
- **Storage**: AWS S3 (PR diffs + artifacts)
- **Cache/Queue**: AWS ElastiCache Redis
- **Compute**: AWS EC2 (t3.small)
- **IaC**: Terraform

## Local Development

```bash
# 1. Copy and fill in env vars
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. API is available at http://localhost:8000
# 5. Swagger UI at http://localhost:8000/docs
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest --cov=app
```

## Deployment

See `infra/` for Terraform configuration and `scripts/` for EC2 bootstrap and deploy scripts.
CI/CD is handled by GitHub Actions (`.github/workflows/`).

## GitHub Secrets

The following secrets must be configured in the GitHub repository
(Settings → Secrets and variables → Actions) before CI/CD will work.

### Required for deploy workflow

| Secret | Description |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | ARN of the GitHub Actions OIDC deploy role — output by `terraform apply` as `github_deploy_role_arn` |
| `AWS_REGION` | AWS region (e.g. `us-east-1`) |
| `ECR_REGISTRY` | ECR registry hostname (e.g. `123456789.dkr.ecr.us-east-1.amazonaws.com`) |
| `EC2_HOST` | Public IP or DNS of the EC2 instance |
| `EC2_USER` | SSH user on EC2 (e.g. `ec2-user`) |
| `SSH_PRIVATE_KEY` | Private key corresponding to the EC2 key pair |

### Notes

- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are NOT used —
  authentication is via OIDC (`AWS_DEPLOY_ROLE_ARN`).
- The OIDC trust policy in `infra/iam.tf` must be updated with your
  GitHub org and repo name, then `terraform apply` run, before the
  deploy workflow will authenticate successfully.
- `ECR_REPOSITORY` is hardcoded to `devpulse` in `deploy.yml` and
  does not need to be a secret.
