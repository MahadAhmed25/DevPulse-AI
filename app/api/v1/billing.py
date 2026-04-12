from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.config import get_settings
from app.database import get_db
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.services.stripe_service import StripeService

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter()


@router.post("/checkout/{tier}")
async def create_checkout_session(
    tier: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a Stripe Checkout session for the given tier (pro | team)."""
    if tier not in ("pro", "team"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier")

    price_id = settings.STRIPE_PRICE_PRO if tier == "pro" else settings.STRIPE_PRICE_TEAM
    stripe_service = StripeService()
    session_url = await stripe_service.create_checkout_session(
        user=current_user,
        price_id=price_id,
        success_url=f"{settings.FRONTEND_URL}/billing/success",
        cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
    )
    return {"checkout_url": session_url}


@router.post("/portal")
async def create_billing_portal(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Create a Stripe billing portal session for the current user."""
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found",
        )
    stripe_service = StripeService()
    portal_url = await stripe_service.create_portal_session(
        customer_id=current_user.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/settings",
    )
    return {"portal_url": portal_url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Handle Stripe webhook events (subscription lifecycle)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe_service = StripeService()
    try:
        await stripe_service.handle_webhook(payload, sig_header, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature")
    return {"status": "ok"}


_TIER_LIMITS: dict[str, dict[str, int | None]] = {
    "free":  {"review_limit": 3,    "repo_limit": 1},
    "pro":   {"review_limit": None, "repo_limit": 5},
    "team":  {"review_limit": None, "repo_limit": None},
}


@router.get("/status")
async def billing_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return current billing tier, usage, and limits."""
    tier = current_user.subscription_tier
    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])

    start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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

    repo_count = (
        await db.execute(
            select(func.count()).where(Repository.owner_id == current_user.id)
        )
    ).scalar_one()

    return {
        "tier": tier,
        "reviews_this_month": reviews_this_month,
        "review_limit": limits["review_limit"],
        "repo_count": repo_count,
        "repo_limit": limits["repo_limit"],
    }
