# Redis — Why We Use Redis Cloud Instead of ElastiCache

## Decision

DevPulse uses **Redis Cloud free tier** instead of AWS ElastiCache for the
Celery broker and result backend.

## Rationale

| Option | Cost | Notes |
|---|---|---|
| AWS ElastiCache (cache.t3.micro) | ~$12–15/month | No free tier |
| Redis Cloud free tier | $0 | 30MB managed Redis, production-grade |

ElastiCache has no free tier. For a portfolio project that needs to demonstrate
real infrastructure without burning money, Redis Cloud's free 30MB database is
production-grade and more than sufficient for the Celery workload.

## How to Set Up

1. Go to [redis.io/try-free](https://redis.io/try-free) and create a free account
2. Create a new database — select the free 30MB tier
3. Copy the **Public endpoint** connection string (format: `redis://:<password>@<host>:<port>`)
4. Add it to your environment files:
   - `.env` (local dev): `REDIS_URL=redis://:<password>@<host>:<port>`
   - `.env.prod` (production): same value

## Migration Path

If DevPulse scales to real production traffic, migrate by:
1. Provision an ElastiCache cluster via Terraform (commented stub below)
2. Update `REDIS_URL` in `.env.prod` to the ElastiCache endpoint
3. No code changes required — the app reads `REDIS_URL` at startup

```hcl
# Uncomment and apply when ready to migrate off Redis Cloud
# resource "aws_elasticache_cluster" "redis" {
#   cluster_id           = "devpulse-redis"
#   engine               = "redis"
#   node_type            = "cache.t3.micro"
#   num_cache_nodes      = 1
#   parameter_group_name = "default.redis7"
#   subnet_group_name    = aws_elasticache_subnet_group.main.name
#   security_group_ids   = [aws_security_group.redis.id]
# }
```
