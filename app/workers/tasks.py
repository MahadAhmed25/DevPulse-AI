import asyncio
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.repository import Repository
from app.services.rag_service import RAGService
from app.services.review_service import ReviewService
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(  # type: ignore[misc]
    name="app.workers.tasks.run_pr_review",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_pr_review(self, pr_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Celery task: run the full review pipeline for a pull request."""
    logger.info("Starting PR review task", pr_id=pr_id, attempt=self.request.retries + 1)

    async def _execute() -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            service = ReviewService(db)
            review = await service.run_review(pr_id)
            await db.commit()
            return {"review_id": str(review.id), "pr_id": pr_id}

    try:
        return _run_async(_execute())  # type: ignore[no-any-return, no-untyped-call]
    except Exception as exc:
        logger.error("PR review task failed", pr_id=pr_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(  # type: ignore[misc]
    name="app.workers.tasks.index_repository",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def index_repository(
    self: Any, repo_id: str, full_name: str, encrypted_token: str
) -> dict[str, Any]:
    """Celery task: fetch and index an entire repository into pgvector via Bedrock embeddings."""
    logger.info("Starting indexing task", repo_id=repo_id)

    async def _execute() -> dict[str, Any]:
        from app.utils.security import decrypt_token

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Repository).where(Repository.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise ValueError(f"Repository {repo_id} not found")

            repo.index_status = "indexing"
            await db.flush()

            access_token = decrypt_token(encrypted_token)
            rag = RAGService(db)
            await rag.index_repository(UUID(repo_id), full_name, access_token)
            await db.commit()
            return {"repo_id": repo_id}

    try:
        return _run_async(_execute())  # type: ignore[no-any-return, no-untyped-call]
    except Exception as exc:
        error_str = str(exc)

        async def _mark_failed() -> None:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Repository).where(Repository.id == repo_id)
                )
                repo = result.scalar_one_or_none()
                if repo:
                    repo.index_status = "failed"
                    repo.index_error = error_str
                    await db.commit()

        _run_async(_mark_failed())  # type: ignore[no-untyped-call]
        logger.error("Indexing task failed", repo_id=repo_id, error=error_str)
        raise self.retry(exc=exc)
