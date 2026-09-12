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
            "review_sample_rate": 0.1,
            "monthly_budget_usd": 300,
        },
        headers=headers,
    )
    resp = await client.get("/api/settings/thresholds", headers=headers)
    assert resp.json()["auto_accept_threshold"] == 0.95
    assert resp.json()["review_sample_rate"] == 0.1


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
            "review_sample_rate": 0.1,
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


# ── 「测试连接」必须按能力自适应 ────────────────────────────────
# 实测事故：embedding provider（embo-01）点测试连接一律报
# 400 unknown model，因为按钮只会打 chat 接口，管理员会误以为 key 坏了。


def _provider_payload(model: str = "embo-01") -> dict:
    return {"name": f"p-{model}", "kind": "minimax", "model": model, "api_key": "sk-x"}


async def _make_provider(client, headers, model: str = "embo-01") -> int:
    resp = await client.post("/api/settings/providers", json=_provider_payload(model), headers=headers)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_embedding_only_provider_reports_success(client, db_session):
    """chat 打不通但 embedding 打得通，应当报成功并说明是向量模型。"""
    from unittest.mock import AsyncMock, patch

    from app.clauses.models import EMBEDDING_DIM
    from app.llm.providers.base import EmbeddingResponse, ProviderError

    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _make_provider(client, headers)

    fake = AsyncMock()
    fake.complete = AsyncMock(side_effect=ProviderError("上游返回 400: unknown model", retryable=False))
    fake.embed = AsyncMock(
        return_value=EmbeddingResponse(vectors=[[0.1] * EMBEDDING_DIM], tokens_in=3)
    )
    with patch("app.llm.router.build_provider", return_value=fake):
        body = (await client.post(f"/api/settings/providers/{config_id}/test", headers=headers)).json()

    assert body["ok"] is True
    assert body["capability"] == "embedding"
    assert "1536" in body["message"]


@pytest.mark.asyncio
async def test_chat_provider_is_not_probed_for_embeddings(client, db_session):
    """chat 打通就该收手，不必再花一次 embedding 的钱。"""
    from unittest.mock import AsyncMock, patch

    from app.llm.providers.base import CompletionResponse

    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _make_provider(client, headers, model="MiniMax-M2")

    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=CompletionResponse(text="ok", tokens_in=1, tokens_out=1))
    fake.embed = AsyncMock()
    with patch("app.llm.router.build_provider", return_value=fake):
        body = (await client.post(f"/api/settings/providers/{config_id}/test", headers=headers)).json()

    assert body["capability"] == "chat"
    fake.embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_dimension_is_caught_before_it_reaches_the_database(client, db_session):
    """维度对不上要在这里就说清楚，等写库时才炸就太晚了。"""
    from unittest.mock import AsyncMock, patch

    from app.llm.providers.base import EmbeddingResponse, ProviderError

    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _make_provider(client, headers, model="text-embedding-3-large")

    fake = AsyncMock()
    fake.complete = AsyncMock(side_effect=ProviderError("400", retryable=False))
    fake.embed = AsyncMock(return_value=EmbeddingResponse(vectors=[[0.1] * 3072], tokens_in=1))
    with patch("app.llm.router.build_provider", return_value=fake):
        body = (await client.post(f"/api/settings/providers/{config_id}/test", headers=headers)).json()

    assert body["ok"] is False
    assert "3072" in body["message"] and "1536" in body["message"]


@pytest.mark.asyncio
async def test_both_capabilities_failing_reports_both_reasons(client, db_session):
    from unittest.mock import AsyncMock, patch

    from app.llm.providers.base import ProviderError

    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _make_provider(client, headers)

    fake = AsyncMock()
    fake.complete = AsyncMock(side_effect=ProviderError("401 invalid api key", retryable=False))
    fake.embed = AsyncMock(side_effect=ProviderError("401 invalid api key", retryable=False))
    with patch("app.llm.router.build_provider", return_value=fake):
        body = (await client.post(f"/api/settings/providers/{config_id}/test", headers=headers)).json()

    assert body["ok"] is False
    assert "chat:" in body["message"] and "embedding:" in body["message"]


# ── provider 删除 ──────────────────────────────────────────────
# 这张表此前只进不出：每次 e2e 冒烟留一行，开发库攒到 33 条，只能写 SQL 清。
# 它不是审计证据，删掉不会让任何历史记录指向空气——llm_call.provider_config_id
# 是 ON DELETE SET NULL。但**被任务路由指着的不能删**，否则那个任务直接哑掉。


async def _named_provider(client, headers, name: str) -> int:
    """本节要按名字认人，不能复用上面那个按 model 建的 _make_provider。"""
    resp = await client.post(
        "/api/settings/providers",
        json={"name": name, "kind": "openai", "model": "gpt-4o", "api_key": "sk-abcdefgh1234"},
        headers=headers,
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_an_unused_provider_can_be_deleted(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _named_provider(client, headers, "spare")

    resp = await client.delete(f"/api/settings/providers/{config_id}", headers=headers)

    assert resp.status_code == 204
    listed = (await client.get("/api/settings/providers", headers=headers)).json()
    assert [c["id"] for c in listed] == []


@pytest.mark.asyncio
async def test_a_routed_provider_cannot_be_deleted(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _named_provider(client, headers, "bound")
    await client.put(
        "/api/settings/routing",
        json={"task_key": "control_extract", "provider_config_id": config_id},
        headers=headers,
    )

    resp = await client.delete(f"/api/settings/providers/{config_id}", headers=headers)

    assert resp.status_code == 409
    assert "control_extract" in resp.text
    listed = (await client.get("/api/settings/providers", headers=headers)).json()
    assert [c["id"] for c in listed] == [config_id]


@pytest.mark.asyncio
async def test_deleting_a_provider_is_audited_without_the_key(client, db_session):
    from sqlalchemy import select

    from app.iam.models import AuditLog

    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")
    config_id = await _named_provider(client, headers, "gone")

    await client.delete(f"/api/settings/providers/{config_id}", headers=headers)

    entry = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "provider.delete")
    )
    assert entry is not None
    assert entry.before["name"] == "gone"
    assert "sk-abcdefgh1234" not in str(entry.before)
    assert "api_key" not in str(entry.before)


@pytest.mark.asyncio
async def test_deleting_a_missing_provider_is_a_404(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    headers = await _auth(client, "admin@example.com")

    resp = await client.delete("/api/settings/providers/99999", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_grc_lead_cannot_delete_a_provider(client, db_session):
    await _seed(db_session, Role.ADMIN, "admin@example.com")
    admin_headers = await _auth(client, "admin@example.com")
    config_id = await _named_provider(client, admin_headers, "spare")
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    lead_headers = await _auth(client, "lead@example.com")

    resp = await client.delete(f"/api/settings/providers/{config_id}", headers=lead_headers)

    assert resp.status_code == 403
