import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReviewComment(BaseModel):
    file_path: str
    line_number: int
    severity: str  # bug | security | performance | suggestion | style
    title: str
    body: str


class ReviewResult(BaseModel):
    """Structured output from the LLM — internal use only, not the API response schema."""
    summary: str
    verdict: str  # approve | request_changes | comment
    comments: list[ReviewComment]
    bugs_found: int
    security_issues: int
    suggestions: int
    model_used: str
    tokens_used: int
    processing_time_ms: int


class ReviewRead(BaseModel):
    id: uuid.UUID
    pull_request_id: uuid.UUID
    model_used: str | None
    summary: str | None
    total_comments: int
    bugs_count: int
    suggestions_count: int
    security_flags_count: int
    style_issues_count: int
    tokens_used: int | None
    processing_time_ms: int | None
    posted_to_github: bool
    structured_review: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewList(BaseModel):
    items: list[ReviewRead]
    total: int
