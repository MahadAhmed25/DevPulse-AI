import time
from typing import Any

import boto3
import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("")
async def health_check() -> dict[str, Any]:
    """Fast liveness probe — no external dependencies. Used by load balancer."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "region": settings.AWS_REGION,
    }


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Database connectivity check."""
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        logger.warning("Health DB check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


@router.get("/redis")
async def health_redis() -> dict[str, Any]:
    """Redis connectivity check."""
    start = time.perf_counter()
    client = aioredis.from_url(settings.redis_url_str)
    try:
        await client.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        logger.warning("Health Redis check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}
    finally:
        await client.close()


@router.get("/s3")
async def health_s3() -> dict[str, Any]:
    """S3 bucket accessibility check."""
    try:
        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        return {"status": "ok", "bucket": settings.S3_BUCKET_NAME}
    except Exception as exc:
        logger.warning("Health S3 check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


@router.get("/bedrock")
async def health_bedrock() -> dict[str, Any]:
    """Bedrock availability check — lightweight read-only call, no inference spend."""
    try:
        bedrock = boto3.client("bedrock", region_name=settings.AWS_REGION)
        bedrock.list_foundation_models(byOutputModality="EMBEDDING")
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Health Bedrock check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}
