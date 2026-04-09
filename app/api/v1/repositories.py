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
from app.services.s3_service import S3Service
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
        index_status="indexing",
    )
    db.add(repo)
    await db.flush()

    index_repository.delay(
        str(repo.id), repo.full_name, current_user.github_access_token
    )
    logger.info("Repository added and indexing enqueued", repo_id=str(repo.id), full_name=repo.full_name)
    return repo


@router.get("/{repo_id}", response_model=RepositoryRead)
async def get_repository(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Repository:
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id, Repository.owner_id == current_user.id
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repo


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

    # Delete S3 diff objects for all associated pull requests
    s3 = S3Service()
    for pr in repo.pull_requests:
        if pr.diff_s3_key is not None:
            try:
                s3.delete_object(pr.diff_s3_key)
            except Exception as exc:
                logger.warning("Failed to delete S3 diff", key=pr.diff_s3_key, error=str(exc))

    await db.delete(repo)
    logger.info("Repository removed", repo_id=str(repo_id))


@router.post("/{repo_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_repository(
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

    repo.index_status = "indexing"
    await db.flush()

    index_repository.delay(
        str(repo.id), repo.full_name, current_user.github_access_token
    )
    logger.info("Reindex queued", repo_id=str(repo_id))
    return {"message": "Reindex queued", "repo_id": str(repo_id)}
