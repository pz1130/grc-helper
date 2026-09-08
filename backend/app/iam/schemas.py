from datetime import datetime

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
