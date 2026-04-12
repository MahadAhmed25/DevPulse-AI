import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.pull_request import PullRequest


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Structured output stored as JSONB for flexible querying; large reviews also mirrored to S3
    structured_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    s3_review_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bugs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suggestions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    security_flags_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    style_issues_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_to_github: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_review_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pull_request: Mapped["PullRequest"] = relationship(  # noqa: F821
        "PullRequest", back_populates="reviews"
    )
