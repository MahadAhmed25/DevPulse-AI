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
