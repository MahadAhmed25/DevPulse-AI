import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.database import get_db
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryList, RepositoryRead
from app.services import github_service
from app.services.s3_service import S3Service
from app.utils.security import decrypt_token
from app.workers.tasks import index_repository, run_pr_review

logger = structlog.get_logger(__name__)
router = APIRouter()

FREE_TIER_MONTHLY_LIMIT = 3


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


@router.post("/{repo_id}/prs/{pr_number}/review", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pr_review(
    repo_id: uuid.UUID,
    pr_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Manually trigger an AI review for a specific PR."""
    repo_result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id, Repository.owner_id == current_user.id
        )
    )
    repo = repo_result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    # Free tier monthly limit check
    if current_user.subscription_tier == "free":
        start_of_month = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        reviews_this_month = (
            await db.execute(
                select(func.count(Review.id))
                .select_from(Review)
                .join(PullRequest, Review.pull_request_id == PullRequest.id)
                .join(Repository, PullRequest.repository_id == Repository.id)
                .where(
                    Repository.owner_id == current_user.id,
                    Review.created_at >= start_of_month,
                )
            )
        ).scalar_one()
        if reviews_this_month >= FREE_TIER_MONTHLY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"error": "monthly_limit_reached", "upgrade_url": "/billing"},
            )

    # Fetch PR metadata from GitHub
    access_token = decrypt_token(current_user.github_access_token or "")
    pr_data = await github_service.get_pull_request(access_token, repo.full_name, pr_number)

    # Get or create PullRequest row
    pr_result = await db.execute(
        select(PullRequest).where(
            PullRequest.repository_id == repo_id,
            PullRequest.github_pr_number == pr_number,
        )
    )
    pr = pr_result.scalar_one_or_none()
    if pr is None:
        pr = PullRequest(
            repository_id=repo_id,
            github_pr_number=pr_number,
            title=pr_data.get("title", ""),
            author_github_login=pr_data.get("user", {}).get("login", ""),
            base_branch=pr_data.get("base", {}).get("ref", ""),
            head_branch=pr_data.get("head", {}).get("ref", ""),
            files_changed=pr_data.get("changed_files"),
            lines_added=pr_data.get("additions"),
            lines_removed=pr_data.get("deletions"),
            status="pending",
        )
        db.add(pr)
    else:
        pr.status = "pending"

    await db.flush()

    run_pr_review.delay(str(pr.id))
    logger.info("PR review queued", pr_id=str(pr.id), repo=repo.full_name, pr_number=pr_number)
    return {"message": "Review queued", "pr_id": str(pr.id)}
