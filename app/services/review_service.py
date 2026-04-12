from uuid import UUID

import boto3
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.pull_request import PullRequest
from app.models.review import Review
from app.services import github_service
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.s3_service import S3Service
from app.utils.security import decrypt_token

logger = structlog.get_logger(__name__)
settings = get_settings()

MAX_DIFF_CHARS = 60_000


class ReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._s3 = S3Service()
        self._llm = LLMService()

    async def run_review(
        self,
        pr_id: UUID,
        repo_id: UUID,
        pr_number: int,
        full_name: str,
        pr_title: str,
        encrypted_token: str,
        use_sonnet: bool = False,
    ) -> Review:
        """Full review pipeline: fetch diff → RAG → LLM → GitHub → S3 → RDS."""
        pr_result = await self._db.execute(select(PullRequest).where(PullRequest.id == pr_id))
        pr = pr_result.scalar_one_or_none()
        if pr is None:
            raise ValueError(f"PullRequest {pr_id} not found")

        # a. Mark as reviewing
        pr.status = "reviewing"
        await self._db.flush()

        try:
            # b. Decrypt token
            access_token = decrypt_token(encrypted_token)

            # c. Fetch diff
            diff = await github_service.get_pr_diff(access_token, full_name, pr_number)

            # d. Empty diff — skip review entirely
            if not diff.strip():
                pr.status = "complete"
                review = Review(
                    pull_request_id=pr_id,
                    summary="No changes to review.",
                    total_comments=0,
                    bugs_count=0,
                    suggestions_count=0,
                    security_flags_count=0,
                    style_issues_count=0,
                    posted_to_github=False,
                )
                self._db.add(review)
                await self._db.flush()
                logger.info("Empty diff, skipping review", pr_id=str(pr_id))
                return review

            # e. Truncate large diffs
            if len(diff) > MAX_DIFF_CHARS:
                logger.warning(
                    "Diff truncated",
                    pr_id=str(pr_id),
                    original_len=len(diff),
                    truncated_to=MAX_DIFF_CHARS,
                )
                diff = diff[:MAX_DIFF_CHARS]

            # f. Upload raw diff to S3
            pr.diff_s3_key = self._s3.upload_diff(pr.id, diff)
            await self._db.flush()

            # g. Build RAG search query
            search_query = f"{pr_title}\n{diff[:500]}"

            # h. Retrieve codebase context
            rag = RAGService(self._db)
            context_chunks = await rag.retrieve_context(repo_id, search_query, k=8)

            # i. LLM review
            review_result = await self._llm.generate_code_review(
                diff=diff,
                context_chunks=context_chunks,
                pr_title=pr_title,
                use_sonnet=use_sonnet,
            )

            # j. Post inline comments to GitHub
            github_comments = [
                {
                    "path": c.file_path,
                    "line": c.line_number,
                    "body": f"**[{c.severity}] {c.title}**\n\n{c.body}",
                }
                for c in review_result.comments
            ]
            github_review_id = await github_service.post_pr_review(
                access_token=access_token,
                full_name=full_name,
                pr_number=pr_number,
                body=review_result.summary,
                comments=github_comments,
            )

            # k & l. Save Review record to RDS
            review = Review(
                pull_request_id=pr_id,
                model_used=review_result.model_used,
                structured_review=review_result.model_dump(),
                summary=review_result.summary,
                total_comments=len(review_result.comments),
                bugs_count=review_result.bugs_found,
                suggestions_count=review_result.suggestions,
                security_flags_count=review_result.security_issues,
                style_issues_count=sum(1 for c in review_result.comments if c.severity == "style"),
                tokens_used=review_result.tokens_used,
                processing_time_ms=review_result.processing_time_ms,
                posted_to_github=True,
                github_review_id=github_review_id,
            )
            self._db.add(review)
            await self._db.flush()

            # Upload full review JSON to S3
            review.s3_review_key = self._s3.upload_review(review.id, review_result.model_dump())

            # m. Mark PR complete
            pr.status = "complete"
            await self._db.flush()

            logger.info(
                "Review complete",
                pr_id=str(pr_id),
                review_id=str(review.id),
                verdict=review_result.verdict,
                comments=len(review_result.comments),
                tokens=review_result.tokens_used,
            )

            if settings.is_production:
                try:
                    boto3.client("cloudwatch", region_name=settings.AWS_REGION).put_metric_data(
                        Namespace="DevPulse",
                        MetricData=[
                            {
                                "MetricName": "ReviewCompleted",
                                "Dimensions": [
                                    {"Name": "Environment", "Value": settings.ENVIRONMENT}
                                ],
                                "Value": 1,
                                "Unit": "Count",
                            }
                        ],
                    )
                except Exception:
                    logger.warning("Failed to emit ReviewCompleted metric to CloudWatch")

            return review

        except Exception as exc:
            pr.status = "failed"
            await self._db.flush()
            logger.error("Review failed", pr_id=str(pr_id), error=str(exc))

            if settings.is_production:
                try:
                    boto3.client("cloudwatch", region_name=settings.AWS_REGION).put_metric_data(
                        Namespace="DevPulse",
                        MetricData=[
                            {
                                "MetricName": "ReviewFailed",
                                "Dimensions": [
                                    {"Name": "Environment", "Value": settings.ENVIRONMENT}
                                ],
                                "Value": 1,
                                "Unit": "Count",
                            }
                        ],
                    )
                except Exception:
                    logger.warning("Failed to emit ReviewFailed metric to CloudWatch")

            raise
