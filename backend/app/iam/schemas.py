from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.iam.permissions import Role


class UserOut(BaseModel):
    """对外的用户表示。刻意不含 password_hash——不给它任何泄漏路径。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    role: Role
    is_active: bool
    expires_at: datetime | None
    engagement_scope_id: int | None
    created_at: datetime


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    role: Role
    password: str = Field(min_length=8)
    expires_at: datetime | None = None
    engagement_scope_id: int | None = None


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    engagement_scope_id: int | None = None
    password: str | None = Field(default=None, min_length=8)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    at: datetime
