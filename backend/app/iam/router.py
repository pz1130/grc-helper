from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Unauthorized
from app.iam.deps import CurrentUser
from app.iam.models import User
from app.iam.schemas import LoginIn, LoginOut, UserOut
from app.iam.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)) -> LoginOut:
    user = await session.scalar(select(User).where(User.email == payload.email))
    # 统一的失败信息，不区分"用户不存在"与"密码错误"，避免账号枚举。
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("邮箱或密码不正确")
    if not user.is_active:
        raise Unauthorized("邮箱或密码不正确")
    from datetime import UTC, datetime

    if user.expires_at is not None and user.expires_at <= datetime.now(UTC):
        raise Unauthorized("邮箱或密码不正确")

    return LoginOut(
        access_token=create_access_token(user.id, user.role),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
