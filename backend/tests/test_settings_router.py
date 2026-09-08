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
async def test_create_provider_never_returns_plaintext_key(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.post(
        "/api/settings/providers",
        json={
            "name": "prod-anthropic",
            "kind": "anthropic",
            "model": "claude-opus-5",
            "api_key": "sk-ant-supersecret",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert "sk-ant-supersecret" not in resp.text
    assert resp.json()["api_key_masked"] == "…cret"


@pytest.mark.asyncio
async def test_list_providers_masks_keys(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    await client.post(
        "/api/settings/providers",
        json={"name": "p", "kind": "openai", "model": "gpt-4o", "api_key": "sk-abcdefgh1234"},
        headers=headers,
    )
    resp = await client.get("/api/settings/providers", headers=headers)
    assert "sk-abcdefgh1234" not in resp.text


@pytest.mark.asyncio
async def test_grc_lead_cannot_touch_provider_config(client, db_session):
    """spec §8.1：GRC Lead 碰不到 AI 配置。"""
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    headers = await _auth(client, "lead@example.com")
    assert (await client.get("/api/settings/providers", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_provider_change_is_audited_without_the_key(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    await client.post(
        "/api/settings/providers",
        json={"name": "p", "kind": "openai", "model": "gpt-4o", "api_key": "sk-leakcheck"},
        headers=headers,
    )
    log = await client.get("/api/audit-log?entity_type=LLMProviderConfig", headers=headers)
    assert any(e["action"] == "provider.create" for e in log.json())
    assert "sk-leakcheck" not in log.text


@pytest.mark.asyncio
async def test_redaction_preview_shows_what_would_be_sent(client, db_session):
    """spec §6.2：调用前可预览脱敏后实际发送的内容。"""
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    await client.post(
        "/api/settings/redaction",
        json={
            "ruleset": "generation",
            "pattern_type": "regex",
            "pattern": r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
            "replacement_prefix": "IP",
        },
        headers=headers,
    )
    resp = await client.post(
        "/api/settings/redaction/preview",
        json={"ruleset": "generation", "text": "跳板机 10.20.30.40 需复核"},
        headers=headers,
    )
    body = resp.json()
    assert "10.20.30.40" not in body["redacted"]
    assert "[[IP_1]]" in body["redacted"]
    assert body["hits"] == {"IP": 1}


@pytest.mark.asyncio
async def test_thresholds_roundtrip(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    await client.put(
        "/api/settings/thresholds",
        json={
            "auto_accept_threshold": 0.95,
            "force_manual_threshold": 0.5,
            "monthly_budget_usd": 300,
        },
        headers=headers,
    )
    resp = await client.get("/api/settings/thresholds", headers=headers)
    assert resp.json()["auto_accept_threshold"] == 0.95


@pytest.mark.asyncio
async def test_threshold_ordering_is_enforced(client, db_session):
    """自动接受阈值必须高于强制人工阈值，否则语义矛盾。"""
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    resp = await client.put(
        "/api/settings/thresholds",
        json={
            "auto_accept_threshold": 0.4,
            "force_manual_threshold": 0.8,
            "monthly_budget_usd": 300,
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_usage_endpoint_readable_by_viewer(client, db_session):
    await _seed(db_session, Role.VIEWER, "v@example.com")
    headers = await _auth(client, "v@example.com")
    resp = await client.get("/api/settings/usage", headers=headers)
    assert resp.status_code == 200
    assert "month_to_date_cost" in resp.json()
