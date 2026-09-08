from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Conflict, NotFound, Unauthorized
from app.iam.audit import record
from app.iam.deps import CurrentUser, require
from app.iam.models import AuditLog, User
from app.iam.permissions import Permission, Role
from app.iam.schemas import AuditLogOut, LoginIn, LoginOut, UserCreateIn, UserOut, UserUpdateIn
from app.iam.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)) -> LoginOut:
    user = await session.scalar(select(User).where(User.email == payload.email))

    # 统一的失败信息，不区分"用户不存在"与"密码错误"，避免账号枚举。
    # 账号不存在时也必须跑一次等价成本的校验：只统一文案不统一耗时，
    # 攻击者仍能用响应时间把有效邮箱扫出来。
    if user is None:
        dummy_verify(payload.password)
        raise Unauthorized("邮箱或密码不正确")
    if not verify_password(payload.password, user.password_hash):
        raise Unauthorized("邮箱或密码不正确")
    if not user.is_active:
        raise Unauthorized("邮箱或密码不正确")
    if user.expires_at is not None and user.expires_at <= datetime.now(UTC):
        raise Unauthorized("邮箱或密码不正确")

    return LoginOut(
        access_token=create_access_token(user.id, user.role),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


users_router = APIRouter(prefix="/api/users", tags=["users"])


def _snapshot(user: User) -> dict:
    return {
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "is_active": user.is_active,
        "expires_at": user.expires_at.isoformat() if user.expires_at else None,
        "engagement_scope_id": user.engagement_scope_id,
    }


async def _would_orphan_admin(
    session: AsyncSession, target: User, data: dict
) -> bool:
    """这次改动会不会让系统失去最后一名启用的管理员。

    覆盖两种走法：把自己降级/停用，以及把别人降级/停用——真正要守的
    不变量是"系统里始终至少有一名启用的 admin"，不只是"别动自己"。
    """
    if not (target.role is Role.ADMIN and target.is_active):
        return False

    stays_admin = data.get("role", target.role) is Role.ADMIN
    stays_active = data.get("is_active", target.is_active)
    if stays_admin and stays_active:
        return False

    others = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role == Role.ADMIN,
            User.is_active.is_(True),
            User.id != target.id,
        )
    )
    return not others


@users_router.get("", response_model=list[UserOut])
async def list_users(
    _: User = Depends(require(Permission.USER_MANAGE)),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    return list(await session.scalars(select(User).order_by(User.id)))


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateIn,
    request: Request,
    actor: User = Depends(require(Permission.USER_MANAGE)),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = User(
        email=payload.email,
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        expires_at=payload.expires_at,
        engagement_scope_id=payload.engagement_scope_id,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        # 不回滚的话 session 停在失效态，这个请求里后续任何一次用它都会炸。
        await session.rollback()
        raise Conflict("该邮箱已存在") from exc

    await record(
        session,
        user=actor,
        action="user.create",
        entity_type="User",
        entity_id=user.id,
        after=_snapshot(user),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return user


@users_router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdateIn,
    request: Request,
    actor: User = Depends(require(Permission.USER_MANAGE)),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")

    before = _snapshot(user)
    data = payload.model_dump(exclude_unset=True)
    if await _would_orphan_admin(session, user, data):
        raise Conflict("系统必须保留至少一名启用的管理员，无法执行该改动")
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(user, field, value)
    await session.flush()

    await record(
        session,
        user=actor,
        action="user.update",
        entity_type="User",
        entity_id=user.id,
        before=before,
        after=_snapshot(user),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return user


audit_router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])


@audit_router.get("", response_model=list[AuditLogOut])
async def list_audit_log(
    entity_type: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    _: User = Depends(require(Permission.AUDIT_LOG_READ)),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500)).offset(offset)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return list(await session.scalars(stmt))
