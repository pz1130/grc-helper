from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.config import get_settings
from app.errors import Unauthorized
from app.iam.permissions import Role

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, VerificationError):
        return False


@dataclass(frozen=True)
class TokenPayload:
    sub: int
    role: Role
    exp: int


def create_access_token(user_id: int, role: Role) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "role": role.value, "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise Unauthorized("令牌无效或已过期") from exc
    return TokenPayload(sub=int(raw["sub"]), role=Role(raw["role"]), exp=raw["exp"])
