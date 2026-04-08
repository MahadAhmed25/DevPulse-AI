import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReviewComment(BaseModel):
    path: str
    line: int
    body: str
    severity: str  # bug | suggestion | security | style


class ReviewRead(BaseModel):
    id: uuid.UUID
    pull_request_id: uuid.UUID
    summary: str | None
    bugs_count: int
    suggestions_count: int
    security_flags_count: int
    style_issues_count: int
    model_used: str | None
    tokens_used: int | None
    structured_review: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewList(BaseModel):
    items: list[ReviewRead]
    total: int
