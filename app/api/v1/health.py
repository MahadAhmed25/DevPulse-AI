from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()


@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Liveness + database connectivity check used by load balancer and CI."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
