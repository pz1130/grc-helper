from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt, mask, decrypt
from app.db import get_session
from app.errors import AppError, NotFound
from app.iam.audit import record
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.llm import budget
from app.llm.models import AppSetting, LLMCall, LLMProviderConfig, RedactionRule, TaskRouting
from app.llm.providers.base import CompletionRequest, ProviderError
from app.llm.providers.factory import build_provider
from app.llm.redaction import load_engine
from app.llm.schemas import (
    PreviewIn,
    PreviewOut,
    ProviderCreateIn,
    ProviderOut,
    ProviderUpdateIn,
    RedactionRuleIn,
    RedactionRuleOut,
    RoutingIn,
    RoutingOut,
    ThresholdsIn,
    ThresholdsOut,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_THRESHOLD_KEYS = ("auto_accept_threshold", "force_manual_threshold", "monthly_budget_usd")


def _to_out(config: LLMProviderConfig) -> ProviderOut:
    return ProviderOut(
        id=config.id,
        name=config.name,
        kind=config.kind,
        model=config.model,
        base_url=config.base_url,
        enabled=config.enabled,
        is_fallback=config.is_fallback,
        monthly_budget=config.monthly_budget,
        api_key_masked=mask(decrypt(config.api_key_encrypted)),
    )


def _snapshot(config: LLMProviderConfig) -> dict:
    # 刻意不含 api_key_encrypted——审计日志是永久的，密钥不许进去
    return {
        "name": config.name,
        "kind": config.kind.value,
        "model": config.model,
        "base_url": config.base_url,
        "enabled": config.enabled,
        "is_fallback": config.is_fallback,
    }


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(
    _: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderOut]:
    configs = await session.scalars(select(LLMProviderConfig).order_by(LLMProviderConfig.id))
    return [_to_out(c) for c in configs]


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreateIn,
    request: Request,
    actor: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    config = LLMProviderConfig(
        name=payload.name,
        kind=payload.kind,
        model=payload.model,
        base_url=payload.base_url,
        api_key_encrypted=encrypt(payload.api_key),
        is_fallback=payload.is_fallback,
        monthly_budget=payload.monthly_budget,
    )
    session.add(config)
    await session.flush()
    await record(
        session,
        user=actor,
        action="provider.create",
        entity_type="LLMProviderConfig",
        entity_id=config.id,
        after=_snapshot(config),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return _to_out(config)


@router.patch("/providers/{config_id}", response_model=ProviderOut)
async def update_provider(
    config_id: int,
    payload: ProviderUpdateIn,
    request: Request,
    actor: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    config = await session.get(LLMProviderConfig, config_id)
    if config is None:
        raise NotFound("provider 不存在")

    before = _snapshot(config)
    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        config.api_key_encrypted = encrypt(data.pop("api_key"))
    for field, value in data.items():
        setattr(config, field, value)
    await session.flush()

    await record(
        session,
        user=actor,
        action="provider.update",
        entity_type="LLMProviderConfig",
        entity_id=config.id,
        before=before,
        after=_snapshot(config),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return _to_out(config)


@router.post("/providers/{config_id}/test")
async def test_provider(
    config_id: int,
    _: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    config = await session.get(LLMProviderConfig, config_id)
    if config is None:
        raise NotFound("provider 不存在")
    try:
        await build_provider(config).complete(
            CompletionRequest(
                system="You are a connectivity probe.",
                prompt="Reply with the single word: ok",
                model=config.model,
                max_tokens=16,
            )
        )
    except ProviderError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "连接正常"}


@router.get("/routing", response_model=list[RoutingOut])
async def list_routing(
    _: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> list[TaskRouting]:
    return list(await session.scalars(select(TaskRouting).order_by(TaskRouting.task_key)))


@router.put("/routing", response_model=RoutingOut)
async def upsert_routing(
    payload: RoutingIn,
    actor: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> TaskRouting:
    routing = await session.scalar(
        select(TaskRouting).where(TaskRouting.task_key == payload.task_key)
    )
    if routing is None:
        routing = TaskRouting(task_key=payload.task_key)
        session.add(routing)
    routing.provider_config_id = payload.provider_config_id
    routing.temperature = payload.temperature
    routing.max_tokens = payload.max_tokens
    await session.flush()
    await record(
        session,
        user=actor,
        action="routing.upsert",
        entity_type="TaskRouting",
        entity_id=routing.id,
        after={"task_key": routing.task_key, "provider_config_id": routing.provider_config_id},
    )
    await session.commit()
    return routing


@router.get("/redaction", response_model=list[RedactionRuleOut])
async def list_rules(
    _: User = Depends(require(Permission.REDACTION_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> list[RedactionRule]:
    return list(
        await session.scalars(
            select(RedactionRule).order_by(RedactionRule.ruleset, RedactionRule.order_index)
        )
    )


@router.post("/redaction", response_model=RedactionRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RedactionRuleIn,
    actor: User = Depends(require(Permission.REDACTION_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> RedactionRule:
    rule = RedactionRule(**payload.model_dump())
    session.add(rule)
    await session.flush()
    await record(
        session,
        user=actor,
        action="redaction.create",
        entity_type="RedactionRule",
        entity_id=rule.id,
        after=payload.model_dump(mode="json"),
    )
    await session.commit()
    return rule


@router.patch("/redaction/{rule_id}", response_model=RedactionRuleOut)
async def update_rule(
    rule_id: int,
    payload: RedactionRuleIn,
    actor: User = Depends(require(Permission.REDACTION_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> RedactionRule:
    rule = await session.get(RedactionRule, rule_id)
    if rule is None:
        raise NotFound("脱敏规则不存在")
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    await session.flush()
    await record(
        session,
        user=actor,
        action="redaction.update",
        entity_type="RedactionRule",
        entity_id=rule.id,
        after=payload.model_dump(mode="json"),
    )
    await session.commit()
    return rule


@router.post("/redaction/preview", response_model=PreviewOut)
async def preview(
    payload: PreviewIn,
    _: User = Depends(require(Permission.REDACTION_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> PreviewOut:
    """spec §6.2 的"发送预览"：让人看到实际会发出去什么。"""
    engine = await load_engine(session, payload.ruleset)
    result = engine.redact(payload.text)
    return PreviewOut(redacted=result.text, hits=result.hits)


@router.get("/thresholds", response_model=ThresholdsOut)
async def get_thresholds(
    _: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> ThresholdsOut:
    values: dict[str, float] = {}
    for key in _THRESHOLD_KEYS:
        setting = await session.get(AppSetting, key)
        values[key] = float(setting.value["value"]) if setting else 0.0
    return ThresholdsOut(**values)


@router.put("/thresholds", response_model=ThresholdsOut)
async def put_thresholds(
    payload: ThresholdsIn,
    actor: User = Depends(require(Permission.LLM_CONFIG_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> ThresholdsOut:
    if payload.auto_accept_threshold <= payload.force_manual_threshold:
        raise AppError("自动接受阈值必须高于强制人工阈值")

    for key in _THRESHOLD_KEYS:
        value = getattr(payload, key)
        setting = await session.get(AppSetting, key)
        if setting is None:
            session.add(AppSetting(key=key, value={"value": value}))
        else:
            setting.value = {"value": value}
    await session.flush()
    await record(
        session,
        user=actor,
        action="thresholds.update",
        entity_type="AppSetting",
        entity_id="thresholds",
        after=payload.model_dump(mode="json"),
    )
    await session.commit()
    return ThresholdsOut(**payload.model_dump())


@router.get("/usage")
async def usage(
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    setting = await session.get(AppSetting, "monthly_budget_usd")
    rows = await session.execute(
        select(LLMCall.task_key, func.sum(LLMCall.cost), func.count()).group_by(LLMCall.task_key)
    )
    return {
        "month_to_date_cost": await budget.month_to_date_cost(session),
        "budget": float(setting.value["value"]) if setting else None,
        "by_task": [
            {"task_key": task, "cost": float(cost or 0), "calls": count}
            for task, cost, count in rows
        ],
    }
