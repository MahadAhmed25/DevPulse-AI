import uuid
from datetime import datetime

from pydantic import BaseModel


class RepositoryBase(BaseModel):
    full_name: str
    default_branch: str = "main"


class RepositoryCreate(RepositoryBase):
    github_repo_id: int


class RepositoryRead(RepositoryBase):
    id: uuid.UUID
    github_repo_id: int
    is_active: bool
    is_indexed: bool
    index_status: str
    last_indexed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RepositoryList(BaseModel):
    items: list[RepositoryRead]
    total: int
