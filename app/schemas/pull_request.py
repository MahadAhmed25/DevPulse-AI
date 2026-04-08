import uuid
from datetime import datetime

from pydantic import BaseModel


class PullRequestRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    github_pr_number: int
    title: str
    author_github_login: str
    base_branch: str
    head_branch: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PullRequestList(BaseModel):
    items: list[PullRequestRead]
    total: int
