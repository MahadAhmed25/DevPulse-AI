from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.utils.security import verify_github_webhook_signature
from app.workers.tasks import run_pr_review

logger = structlog.get_logger(__name__)
router = APIRouter()


@limiter.limit("100/minute", key_func=get_remote_address)
@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(...),
    x_github_event: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive GitHub webhook events. Verifies HMAC signature before processing."""
    payload_bytes = await request.body()

    if not verify_github_webhook_signature(payload_bytes, x_hub_signature_256):
        logger.warning("Invalid webhook signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
        )

    if x_github_event == "ping":
        return {"message": "pong"}

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()
    action: str = payload.get("action", "")

    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    github_repo_id: int = payload["repository"]["id"]
    pr_number: int = payload["pull_request"]["number"]
    pr_title: str = payload["pull_request"]["title"]
    author: str = payload["pull_request"]["user"]["login"]
    base_branch: str = payload["pull_request"]["base"]["ref"]
    head_branch: str = payload["pull_request"]["head"]["ref"]

    result = await db.execute(select(Repository).where(Repository.github_repo_id == github_repo_id))
    repo = result.scalar_one_or_none()
    if repo is None:
        logger.info("Webhook for unregistered repo", github_repo_id=github_repo_id)
        return {"status": "ignored", "reason": "repository not registered"}

    # Upsert the pull request record
    existing_pr = await db.execute(
        select(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.github_pr_number == pr_number,
        )
    )
    pr = existing_pr.scalar_one_or_none()

    if pr is None:
        pr = PullRequest(
            repository_id=repo.id,
            github_pr_number=pr_number,
            title=pr_title,
            author_github_login=author,
            base_branch=base_branch,
            head_branch=head_branch,
            status="pending",
        )
        db.add(pr)
    else:
        pr.status = "pending"

    await db.flush()

    run_pr_review.delay(str(pr.id))

    logger.info(
        "PR review queued",
        pr_id=str(pr.id),
        repo=repo.full_name,
        pr_number=pr_number,
    )
    return {"status": "queued", "pr_id": str(pr.id)}
