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
from app.schemas.review import ReviewList, ReviewRead

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/stats")
async def get_review_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Aggregate review statistics for the current user."""
    stats_result = await db.execute(
        select(
            func.count(Review.id).label("total_reviews"),
            func.coalesce(func.sum(Review.bugs_count), 0).label("total_bugs_found"),
            func.coalesce(func.sum(Review.security_flags_count), 0).label("total_security_issues"),
            func.coalesce(func.avg(Review.total_comments), 0.0).label("avg_comments_per_pr"),
        )
        .select_from(Review)
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(Repository.owner_id == current_user.id)
    )
    row = stats_result.one()

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

    return {
        "total_reviews": row.total_reviews,
        "total_bugs_found": int(row.total_bugs_found),
        "total_security_issues": int(row.total_security_issues),
        "avg_comments_per_pr": float(row.avg_comments_per_pr),
        "reviews_this_month": reviews_this_month,
    }


@router.get("", response_model=ReviewList)
async def list_reviews(
    skip: int = 0,
    limit: int = 20,
    repository_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReviewList:
    query = (
        select(Review)
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(Repository.owner_id == current_user.id)
    )
    count_query = (
        select(func.count())
        .select_from(Review)
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(Repository.owner_id == current_user.id)
    )

    if repository_id:
        query = query.where(Repository.id == repository_id)
        count_query = count_query.where(Repository.id == repository_id)

    total = (await db.execute(count_query)).scalar_one()
    reviews = (
        await db.execute(query.offset(skip).limit(limit).order_by(Review.created_at.desc()))
    ).scalars().all()

    return ReviewList(items=list(reviews), total=total)  # type: ignore[arg-type]


@router.get("/{review_id}", response_model=ReviewRead)
async def get_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Review:
    result = await db.execute(
        select(Review)
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(Review.id == review_id, Repository.owner_id == current_user.id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return review
