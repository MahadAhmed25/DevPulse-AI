import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.services import github_service
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.s3_service import S3Service
from app.utils.security import decrypt_token

logger = structlog.get_logger(__name__)


class ReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._s3 = S3Service()
        self._llm = LLMService()

    async def run_review(self, pr_id: str) -> Review:
        """Full review pipeline: fetch diff → RAG context → LLM → post comments."""
        pr = await self._load_pull_request(pr_id)
        repo = await self._load_repository(str(pr.repository_id))
        user = await self._load_user(str(repo.owner_id))

        pr.status = "processing"
        await self._db.flush()

        try:
            access_token = decrypt_token(user.github_access_token or "")
            diff = await github_service.get_pr_diff(access_token, repo.full_name, pr.github_pr_number)

            # Persist diff to S3
            s3_key = self._s3.upload_diff(pr.id, diff)
            pr.diff_s3_key = s3_key

            # Retrieve RAG context
            rag = RAGService(self._db)
            context = await rag.retrieve_context(str(repo.id), query=diff[:2000])

            # Run LLM review
            structured_review, tokens_used = self._llm.review_pull_request(
                diff=diff,
                rag_context=context,
            )

            comments = structured_review.get("comments", [])
            review = Review(
                pull_request_id=pr.id,
                structured_review=structured_review,
                summary=structured_review.get("summary"),
                bugs_count=sum(1 for c in comments if c.get("severity") == "bug"),
                suggestions_count=sum(1 for c in comments if c.get("severity") == "suggestion"),
                security_flags_count=sum(1 for c in comments if c.get("severity") == "security"),
                style_issues_count=sum(1 for c in comments if c.get("severity") == "style"),
                model_used="claude-haiku-4-5-20251001",
                tokens_used=tokens_used,
            )
            self._db.add(review)
            await self._db.flush()

            # Post back to GitHub
            if comments:
                github_review_id = await github_service.post_pr_review(
                    access_token=access_token,
                    full_name=repo.full_name,
                    pr_number=pr.github_pr_number,
                    body=structured_review.get("summary", ""),
                    comments=comments,
                )
                review.github_review_id = github_review_id

            pr.status = "completed"
            logger.info(
                "Review completed",
                pr_id=pr_id,
                comments=len(comments),
                tokens=tokens_used,
            )
            return review

        except Exception as exc:
            pr.status = "failed"
            logger.error("Review failed", pr_id=pr_id, error=str(exc))
            raise

    async def _load_pull_request(self, pr_id: str) -> PullRequest:
        result = await self._db.execute(
            select(PullRequest).where(PullRequest.id == pr_id)
        )
        pr = result.scalar_one_or_none()
        if pr is None:
            raise ValueError(f"PullRequest {pr_id} not found")
        return pr

    async def _load_repository(self, repo_id: str) -> Repository:
        result = await self._db.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        repo = result.scalar_one_or_none()
        if repo is None:
            raise ValueError(f"Repository {repo_id} not found")
        return repo

    async def _load_user(self, user_id: str) -> User:
        result = await self._db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return user
