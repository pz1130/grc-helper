import pytest

from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password


async def _seed(db_session, role: Role, email: str) -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client, email: str) -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_user_requires_admin(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    headers = await _auth(client, "lead@example.com")
    resp = await client.post(
        "/api/users",
        json={"email": "x@example.com", "name": "X", "role": "viewer", "password": "pw123456"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_creates_user_and_it_is_audited(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.post(
        "/api/users",
        json={
            "email": "auditor@example.com",
            "name": "External Auditor",
            "role": "viewer",
            "password": "pw123456",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "viewer"
    assert "password" not in resp.text

    log = await client.get("/api/audit-log?entity_type=User", headers=headers)
    entries = log.json()
    assert any(e["action"] == "user.create" for e in entries)
    # 密码绝不能出现在审计日志里
    assert "pw123456" not in log.text


@pytest.mark.asyncio
async def test_duplicate_email_conflicts(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    body = {"email": "dup@example.com", "name": "D", "role": "viewer", "password": "pw123456"}
    assert (await client.post("/api/users", json=body, headers=headers)).status_code == 201
    assert (await client.post("/api/users", json=body, headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_patch_user_records_before_and_after(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    target = await _seed(db_session, Role.VIEWER, "target@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.patch(
        f"/api/users/{target.id}", json={"role": "contributor"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "contributor"

    log = await client.get("/api/audit-log?entity_type=User", headers=headers)
    update = next(e for e in log.json() if e["action"] == "user.update")
    assert update["before"]["role"] == "viewer"
    assert update["after"]["role"] == "contributor"


@pytest.mark.asyncio
async def test_audit_log_denied_to_contributor(client, db_session):
    await _seed(db_session, Role.CONTRIBUTOR, "c@example.com")
    headers = await _auth(client, "c@example.com")
    assert (await client.get("/api/audit-log", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_no_delete_endpoint_for_users_or_audit_log(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    assert (await client.delete("/api/users/1", headers=headers)).status_code == 405
    assert (await client.delete("/api/audit-log", headers=headers)).status_code == 405
