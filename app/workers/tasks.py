import asyncio

import structlog
from github import Github

from app.database import AsyncSessionLocal
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


@celery_app.task(
    name="app.workers.tasks.run_pr_review",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_pr_review(self, pr_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Celery task: run the full review pipeline for a pull request."""
    logger.info("Starting PR review task", pr_id=pr_id, attempt=self.request.retries + 1)

    async def _execute() -> dict:
        async with AsyncSessionLocal() as db:
            service = ReviewService(db)
            review = await service.run_review(pr_id)
            await db.commit()
            return {"review_id": str(review.id), "pr_id": pr_id}

    try:
        return _run_async(_execute())
    except Exception as exc:
        logger.error("PR review task failed", pr_id=pr_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.index_repository",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def index_repository(self, repo_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Celery task: clone and index an entire repository into pgvector."""
    from sqlalchemy import select

    from app.models.repository import Repository
    from app.models.user import User

    logger.info("Starting indexing task", repo_id=repo_id)

    async def _execute() -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Repository).where(Repository.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise ValueError(f"Repository {repo_id} not found")

            owner_result = await db.execute(select(User).where(User.id == repo.owner_id))
            user = owner_result.scalar_one_or_none()
            if user is None or not user.github_access_token:
                raise ValueError(f"No GitHub token for user {repo.owner_id}")

            g = Github(user.github_access_token)
            github_repo = g.get_repo(repo.full_name)

            rag = RAGService(db)
            await rag.delete_repository_embeddings(repo_id)

            total_chunks = 0
            # Traverse the default branch tree and index text/code files
            tree = github_repo.get_git_tree(repo.default_branch, recursive=True)
            for item in tree.tree:
                if item.type != "blob":
                    continue
                # Skip large files and binary extensions
                if item.size and item.size > 200_000:
                    continue
                ext = item.path.rsplit(".", 1)[-1] if "." in item.path else ""
                if ext not in {
                    "py", "ts", "tsx", "js", "jsx", "go", "java", "rb",
                    "rs", "cpp", "c", "h", "cs", "php", "swift", "kt",
                    "md", "txt", "yaml", "yml", "toml", "json",
                }:
                    continue

                try:
                    blob = github_repo.get_git_blob(item.sha)
                    import base64
                    content = base64.b64decode(blob.content).decode("utf-8", errors="ignore")
                    n = await rag.index_file(repo_id, item.path, content)
                    total_chunks += n
                except Exception as exc:
                    logger.warning("Skipping file", path=item.path, error=str(exc))

            from datetime import datetime, timezone
            repo.is_indexed = True
            repo.last_indexed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info("Indexing complete", repo_id=repo_id, chunks=total_chunks)
            return {"repo_id": repo_id, "chunks": total_chunks}

    try:
        return _run_async(_execute())
    except Exception as exc:
        logger.error("Indexing task failed", repo_id=repo_id, error=str(exc))
        raise self.retry(exc=exc)
