"""运维命令行。

用法（容器内）：
    python -m app.cli create-admin admin@example.com "Admin" 's3cret-pw'
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_factory
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password


async def create_admin(
    email: str, name: str, password: str, *, session: AsyncSession | None = None
) -> None:
    """幂等：已存在则重置密码并提升为 admin。

    这是管理员把自己锁死之后的唯一退路，所以停用状态和过期时间也要一并清掉，
    只改密码是不够的。
    """

    async def _run(db: AsyncSession) -> None:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    name=name,
                    role=Role.ADMIN,
                    password_hash=hash_password(password),
                )
            )
        else:
            user.role = Role.ADMIN
            user.is_active = True
            user.expires_at = None
            user.password_hash = hash_password(password)
        await db.flush()

    if session is not None:
        await _run(session)
        return

    async with session_factory() as db:
        await _run(db)
        await db.commit()


def main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] != "create-admin":
        print("用法: python -m app.cli create-admin <email> <name> <password>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(create_admin(sys.argv[2], sys.argv[3], sys.argv[4]))
    print(f"管理员已就绪: {sys.argv[2]}")


if __name__ == "__main__":
    main()
