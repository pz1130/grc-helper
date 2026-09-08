import pytest
from sqlalchemy import select

from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password, verify_password


def test_hash_password_is_not_plaintext():
    hashed = hash_password("s3cret-password")
    assert "s3cret-password" not in hashed
    assert hashed.startswith("$argon2")


def test_verify_password_accepts_correct():
    assert verify_password("s3cret-password", hash_password("s3cret-password"))


def test_verify_password_rejects_wrong():
    assert not verify_password("wrong", hash_password("s3cret-password"))


def test_same_password_hashes_differently():
    assert hash_password("same") != hash_password("same")


@pytest.mark.asyncio
async def test_user_can_be_persisted(db_session):
    user = User(
        email="lead@example.com",
        name="GRC Lead",
        role=Role.GRC_LEAD,
        password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()

    found = await db_session.scalar(select(User).where(User.email == "lead@example.com"))
    assert found is not None
    assert found.role is Role.GRC_LEAD
    assert found.is_active is True
    assert found.expires_at is None
