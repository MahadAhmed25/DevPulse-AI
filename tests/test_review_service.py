"""Phase 4 review pipeline tests."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewComment, ReviewResult
from app.services.review_service import ReviewService
from app.utils.security import create_access_token, encrypt_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(
    db: AsyncSession,
    *,
    github_id: int,
    username: str,
    tier: str = "free",
) -> User:
    user = User(
        email=f"{username}@example.com",
        github_id=github_id,
        github_username=username,
        is_active=True,
        subscription_tier=tier,
        github_access_token=encrypt_token("fake-gh-token"),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_repo(
    db: AsyncSession,
    owner: User,
    *,
    github_repo_id: int,
    full_name: str,
) -> Repository:
    repo = Repository(
        owner_id=owner.id,
        github_repo_id=github_repo_id,
        full_name=full_name,
        default_branch="main",
    )
    db.add(repo)
    await db.flush()
    return repo


async def _make_pr(
    db: AsyncSession,
    repo: Repository,
    *,
    pr_number: int = 1,
) -> PullRequest:
    pr = PullRequest(
        repository_id=repo.id,
        github_pr_number=pr_number,
        title="Test PR",
        author_github_login="author",
        base_branch="main",
        head_branch="feature",
        status="pending",
    )
    db.add(pr)
    await db.flush()
    return pr


def _make_review_result(**overrides: Any) -> ReviewResult:
    defaults: dict[str, Any] = {
        "summary": "Looks good.",
        "verdict": "approve",
        "comments": [],
        "bugs_found": 0,
        "security_issues": 0,
        "suggestions": 0,
        "model_used": "claude-haiku-4-5-20251001",
        "tokens_used": 100,
        "processing_time_ms": 500,
    }
    defaults.update(overrides)
    return ReviewResult(**defaults)  # type: ignore[arg-type]


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ---------------------------------------------------------------------------
# Test 1 — full pipeline happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_happy_path(db_session: AsyncSession) -> None:
    """Full pipeline: diff fetched, S3 uploads x2, GitHub post x1, Review saved."""
    user = await _make_user(db_session, github_id=40001, username="pipeline_user")
    repo = await _make_repo(db_session, user, github_repo_id=8800001, full_name="pipeline_user/repo")
    pr = await _make_pr(db_session, repo)

    fake_result = _make_review_result(
        comments=[
            ReviewComment(
                file_path="app/main.py",
                line_number=10,
                severity="bug",
                title="Null check missing",
                body="Add a null check here.",
            )
        ],
        bugs_found=1,
    )

    with (
        patch("app.services.review_service.github_service") as mock_gh,
        patch("app.services.review_service.S3Service") as mock_s3_class,
        patch("app.services.review_service.LLMService") as mock_llm_class,
        patch("app.services.review_service.RAGService") as mock_rag_class,
    ):
        mock_gh.get_pr_diff = AsyncMock(return_value="diff content here")
        mock_gh.post_pr_review = AsyncMock(return_value=99001)

        mock_s3: MagicMock = MagicMock()
        mock_s3.upload_diff.return_value = "diffs/fake-key/diff.txt"
        mock_s3.upload_review.return_value = "reviews/fake-key/review.json"
        mock_s3_class.return_value = mock_s3

        mock_llm: MagicMock = MagicMock()
        mock_llm.generate_code_review = AsyncMock(return_value=fake_result)
        mock_llm_class.return_value = mock_llm

        mock_rag: MagicMock = MagicMock()
        mock_rag.retrieve_context = AsyncMock(return_value=["chunk1", "chunk2"])
        mock_rag_class.return_value = mock_rag

        service = ReviewService(db_session)
        review = await service.run_review(
            pr_id=pr.id,
            repo_id=repo.id,
            pr_number=pr.github_pr_number,
            full_name=repo.full_name,
            pr_title=pr.title,
            encrypted_token=user.github_access_token or "",
        )

    assert review.bugs_count == 1
    assert review.total_comments == 1
    assert review.posted_to_github is True
    assert review.github_review_id == 99001
    assert review.model_used == "claude-haiku-4-5-20251001"
    assert pr.status == "complete"
    mock_s3.upload_diff.assert_called_once()
    mock_s3.upload_review.assert_called_once()
    mock_gh.post_pr_review.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — diff truncation at 60k chars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_truncation_at_60k_chars(db_session: AsyncSession) -> None:
    """Diffs longer than 60,000 chars are truncated before being sent to the LLM."""
    user = await _make_user(db_session, github_id=40002, username="trunc_user")
    repo = await _make_repo(db_session, user, github_repo_id=8800002, full_name="trunc_user/repo")
    pr = await _make_pr(db_session, repo, pr_number=2)

    oversized_diff = "x" * 70_000
    received_diffs: list[str] = []

    async def _capture(diff: str, **_kwargs: Any) -> ReviewResult:
        received_diffs.append(diff)
        return _make_review_result()

    with (
        patch("app.services.review_service.github_service") as mock_gh,
        patch("app.services.review_service.S3Service") as mock_s3_class,
        patch("app.services.review_service.LLMService") as mock_llm_class,
        patch("app.services.review_service.RAGService") as mock_rag_class,
    ):
        mock_gh.get_pr_diff = AsyncMock(return_value=oversized_diff)
        mock_gh.post_pr_review = AsyncMock(return_value=99002)

        mock_s3 = MagicMock()
        mock_s3.upload_diff.return_value = "diffs/key"
        mock_s3.upload_review.return_value = "reviews/key"
        mock_s3_class.return_value = mock_s3

        mock_llm = MagicMock()
        mock_llm.generate_code_review = AsyncMock(side_effect=_capture)
        mock_llm_class.return_value = mock_llm

        mock_rag = MagicMock()
        mock_rag.retrieve_context = AsyncMock(return_value=[])
        mock_rag_class.return_value = mock_rag

        service = ReviewService(db_session)
        await service.run_review(
            pr_id=pr.id,
            repo_id=repo.id,
            pr_number=pr.github_pr_number,
            full_name=repo.full_name,
            pr_title=pr.title,
            encrypted_token=user.github_access_token or "",
        )

    assert len(received_diffs) == 1
    assert len(received_diffs[0]) == 60_000


# ---------------------------------------------------------------------------
# Test 3 — PR status set to "failed" on LLM error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_status_fails_on_llm_error(db_session: AsyncSession) -> None:
    """If the LLM call raises, PR status is set to 'failed' and the exception re-raised."""
    user = await _make_user(db_session, github_id=40003, username="fail_user")
    repo = await _make_repo(db_session, user, github_repo_id=8800003, full_name="fail_user/repo")
    pr = await _make_pr(db_session, repo, pr_number=3)

    with (
        patch("app.services.review_service.github_service") as mock_gh,
        patch("app.services.review_service.S3Service") as mock_s3_class,
        patch("app.services.review_service.LLMService") as mock_llm_class,
        patch("app.services.review_service.RAGService") as mock_rag_class,
    ):
        mock_gh.get_pr_diff = AsyncMock(return_value="some diff")

        mock_s3 = MagicMock()
        mock_s3.upload_diff.return_value = "diffs/key"
        mock_s3_class.return_value = mock_s3

        mock_llm = MagicMock()
        mock_llm.generate_code_review = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        mock_llm_class.return_value = mock_llm

        mock_rag = MagicMock()
        mock_rag.retrieve_context = AsyncMock(return_value=[])
        mock_rag_class.return_value = mock_rag

        service = ReviewService(db_session)
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await service.run_review(
                pr_id=pr.id,
                repo_id=repo.id,
                pr_number=pr.github_pr_number,
                full_name=repo.full_name,
                pr_title=pr.title,
                encrypted_token=user.github_access_token or "",
            )

    assert pr.status == "failed"


# ---------------------------------------------------------------------------
# Test 4 — free tier limit blocks 4th review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_free_tier_limit_blocks_4th_review(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /repositories/{repo_id}/prs/{pr_number}/review returns 402 after 3 reviews."""
    user = await _make_user(db_session, github_id=40004, username="free_tier_user", tier="free")
    repo = await _make_repo(
        db_session, user, github_repo_id=8800004, full_name="free_tier_user/repo"
    )

    for i in range(1, 4):
        pr = await _make_pr(db_session, repo, pr_number=i)
        review = Review(
            pull_request_id=pr.id,
            total_comments=0,
            bugs_count=0,
            suggestions_count=0,
            security_flags_count=0,
            style_issues_count=0,
            posted_to_github=False,
        )
        db_session.add(review)
    await db_session.flush()

    with patch("app.api.v1.repositories.github_service.get_pull_request") as mock_get_pr:
        mock_get_pr.return_value = {
            "title": "PR 4",
            "user": {"login": "author"},
            "base": {"ref": "main"},
            "head": {"ref": "feature-4"},
            "changed_files": 1,
            "additions": 5,
            "deletions": 2,
        }
        response = await client.post(
            f"/api/v1/repositories/{repo.id}/prs/4/review",
            headers=_auth_headers(user),
        )

    assert response.status_code == 402
    data = response.json()
    assert data["detail"]["error"] == "monthly_limit_reached"
    assert "/billing" in data["detail"]["upgrade_url"]
