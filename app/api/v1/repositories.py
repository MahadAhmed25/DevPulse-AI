import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.database import get_db
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryList, RepositoryRead
from app.workers.tasks import index_repository

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=RepositoryList)
async def list_repositories(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RepositoryList:
    total_result = await db.execute(
        select(func.count()).where(Repository.owner_id == current_user.id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Repository)
        .where(Repository.owner_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .order_by(Repository.created_at.desc())
    )
    repos = result.scalars().all()
    return RepositoryList(items=list(repos), total=total)  # type: ignore[arg-type]


@router.post("", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def add_repository(
    payload: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Repository:
    existing = await db.execute(
        select(Repository).where(Repository.github_repo_id == payload.github_repo_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository already registered",
        )

    repo = Repository(
        owner_id=current_user.id,
        github_repo_id=payload.github_repo_id,
        full_name=payload.full_name,
        default_branch=payload.default_branch,
    )
    db.add(repo)
    await db.flush()

    logger.info("Repository added", repo_id=str(repo.id), full_name=repo.full_name)
    return repo


@router.post("/{repo_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def trigger_indexing(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id, Repository.owner_id == current_user.id
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    index_repository.delay(str(repo_id))
    logger.info("Indexing triggered", repo_id=str(repo_id))
    return {"message": "Indexing queued", "repo_id": str(repo_id)}


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_repository(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id, Repository.owner_id == current_user.id
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    await db.delete(repo)
    logger.info("Repository removed", repo_id=str(repo_id))
