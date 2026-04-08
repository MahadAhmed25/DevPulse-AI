import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str | None
    github_username: str | None
    avatar_url: str | None
    subscription_tier: str
    subscription_status: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: EmailStr | None = None
