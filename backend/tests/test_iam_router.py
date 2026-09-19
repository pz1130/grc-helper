import pytest

from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password


async def _seed(db_session, role: Role, email: str, *, is_active: bool = True) -> User:
    user = User(
        email=email,
        name=email,
        role=role,
        password_hash=hash_password("pw123456"),
        is_active=is_active,
    )
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
async def test_user_list_survives_legacy_internal_email(client, db_session):
    """旧库里的 .local 地址可以展示，不能让整张用户表响应校验失败。"""
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    await _seed(db_session, Role.VIEWER, "legacy@grc.local")
    headers = await _auth(client, "admin@example.com")

    resp = await client.get("/api/users", headers=headers)

    assert resp.status_code == 200
    assert any(row["email"] == "legacy@grc.local" for row in resp.json())


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


@pytest.mark.asyncio
async def test_last_active_admin_cannot_demote_self(client, db_session):
    """不变量：系统里始终至少有一名启用的 admin，否则管理面彻底锁死。"""
    admin = await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.patch(f"/api/users/{admin.id}", json={"role": "viewer"}, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_last_active_admin_cannot_deactivate_self(client, db_session):
    admin = await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.patch(
        f"/api/users/{admin.id}", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_cannot_demote_the_other_last_admin(client, db_session):
    """守的是不变量而不是"别动自己"——降别人也会把系统掏空。"""
    actor = await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    await client.patch(f"/api/users/{actor.id}", json={"name": "still admin"}, headers=headers)

    other = await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    resp = await client.patch(f"/api/users/{other.id}", json={"role": "viewer"}, headers=headers)
    assert resp.status_code == 200, "降一个非 admin 不该被拦"


@pytest.mark.asyncio
async def test_admin_can_be_demoted_when_a_backup_admin_exists(client, db_session):
    admin = await _seed(db_session, Role.ADMIN, "admin@example.com")
    await _seed(db_session, Role.ADMIN, "admin2@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.patch(f"/api/users/{admin.id}", json={"role": "viewer"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"


@pytest.mark.asyncio
async def test_deactivated_admin_does_not_count_as_backup(client, db_session):
    admin = await _seed(db_session, Role.ADMIN, "admin@example.com")
    await _seed(db_session, Role.ADMIN, "sleeping@example.com", is_active=False)
    headers = await _auth(client, "admin@example.com")

    resp = await client.patch(f"/api/users/{admin.id}", json={"role": "viewer"}, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_session_remains_usable_after_duplicate_conflict(client, db_session):
    """撞唯一键后必须回滚，否则同一请求周期内 session 已废，后续操作全炸。"""
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    body = {"email": "dup@example.com", "name": "D", "role": "viewer", "password": "pw123456"}
    assert (await client.post("/api/users", json=body, headers=headers)).status_code == 201
    assert (await client.post("/api/users", json=body, headers=headers)).status_code == 409

    other = {"email": "other@example.com", "name": "O", "role": "viewer", "password": "pw123456"}
    assert (await client.post("/api/users", json=other, headers=headers)).status_code == 201
