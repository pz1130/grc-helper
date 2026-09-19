import pytest

from app.llm.budget import BudgetExceeded, check, month_to_date_cost
from app.crypto import encrypt
from app.llm.models import (
    AppSetting,
    LLMCall,
    LLMProviderConfig,
    ProviderKind,
    RulesetName,
)


async def _spend(db_session, amount: float, *, provider_config_id: int | None = None) -> None:
    db_session.add(
        LLMCall(
            provider_config_id=provider_config_id,
            model="claude-opus-5",
            task_key="control_extract",
            prompt_hash="h",
            cost=amount,
            ruleset=RulesetName.GENERATION,
            status="ok",
        )
    )
    await db_session.flush()


async def _provider(db_session, *, name: str, budget: float | None) -> LLMProviderConfig:
    config = LLMProviderConfig(
        name=name,
        kind=ProviderKind.ANTHROPIC,
        model="claude-opus-5",
        api_key_encrypted=encrypt("k"),
        monthly_budget=budget,
    )
    db_session.add(config)
    await db_session.flush()
    return config


async def _budget(db_session, amount: float) -> None:
    # 0004 seeds monthly_budget_usd=200; mutate that row instead of inserting a duplicate PK.
    setting = await db_session.get(AppSetting, "monthly_budget_usd")
    if setting is None:
        db_session.add(AppSetting(key="monthly_budget_usd", value={"value": amount}))
    else:
        setting.value = {"value": amount}
    await db_session.flush()


@pytest.mark.asyncio
async def test_month_to_date_cost_sums_calls(db_session):
    await _spend(db_session, 1.5)
    await _spend(db_session, 2.5)
    assert await month_to_date_cost(db_session) == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_check_passes_below_budget(db_session):
    await _budget(db_session, 100.0)
    await _spend(db_session, 10.0)
    await check(db_session, interactive=False)   # 不抛异常即通过


@pytest.mark.asyncio
async def test_batch_task_blocked_at_full_budget(db_session):
    await _budget(db_session, 10.0)
    await _spend(db_session, 10.0)
    with pytest.raises(BudgetExceeded):
        await check(db_session, interactive=False)


@pytest.mark.asyncio
async def test_interactive_task_survives_full_budget(db_session):
    """spec §9：达 100% 暂停批量任务但保留交互式任务，避免系统完全瘫痪。"""
    await _budget(db_session, 10.0)
    await _spend(db_session, 10.0)
    await check(db_session, interactive=True)   # 不抛异常


@pytest.mark.asyncio
async def test_no_budget_configured_means_unlimited(db_session):
    # 0004 seeds a $200 cap; "no budget configured" requires that row gone.
    existing = await db_session.get(AppSetting, "monthly_budget_usd")
    if existing is not None:
        await db_session.delete(existing)
        await db_session.flush()
    await _spend(db_session, 9999.0)
    await check(db_session, interactive=False)


@pytest.mark.asyncio
async def test_provider_budget_is_actually_enforced(db_session):
    """provider 级预算曾经是个只存不看的死字段——设置页显示成开关但从不生效。"""
    config = await _provider(db_session, name="p", budget=5.0)
    await _spend(db_session, 5.0, provider_config_id=config.id)

    with pytest.raises(BudgetExceeded):
        await check(db_session, interactive=False, provider=config)


@pytest.mark.asyncio
async def test_provider_budget_counts_only_that_provider(db_session):
    config = await _provider(db_session, name="p", budget=5.0)
    other = await _provider(db_session, name="other", budget=None)
    await _spend(db_session, 100.0, provider_config_id=other.id)

    await check(db_session, interactive=False, provider=config)


@pytest.mark.asyncio
async def test_provider_without_budget_is_unlimited(db_session):
    await _budget(db_session, 0)   # 摘掉全局预算，单独验 provider 这一层
    config = await _provider(db_session, name="p", budget=None)
    await _spend(db_session, 9999.0, provider_config_id=config.id)

    await check(db_session, interactive=False, provider=config)


@pytest.mark.asyncio
async def test_provider_budget_still_yields_to_interactive(db_session):
    config = await _provider(db_session, name="p", budget=5.0)
    await _spend(db_session, 5.0, provider_config_id=config.id)

    await check(db_session, interactive=True, provider=config)


# ── 未计价的模型要可见 ── OQ-22 ────────────────────────────────────
#
# `pricing.py` 对未知模型返回 0 是**有意为之**（注释写了：成本统计不准可以接受，
# 让整条流水线挂掉不可接受）。问题不在这个决定，在于**没有任何信号说"这个模型
# 没有价"**：预算卡照常显示 $0.00 / $350.00，预算闸门形同虚设。
#
# 修法不是往价格表里加某个具体模型——价格会变，下一家机构又换模型，那是会过期
# 的数据。要让"未计价"这件事本身可见。


def test_unknown_model_is_reported_as_unpriced_not_as_free():
    from app.llm.pricing import estimate_cost, is_priced

    assert is_priced("claude-opus-5") is True
    assert is_priced("minimax-m3") is False
    # 仍然返回 0 而不是抛异常——这条行为不变
    assert estimate_cost("minimax-m3", 10_000, 10_000) == 0.0


@pytest.mark.asyncio
async def test_usage_counts_calls_that_were_never_priced(db_session):
    """用量接口要能回答"这个月有多少次调用根本没算进成本"。"""
    from app.llm import budget as budget_module

    for model, count in (("claude-opus-5", 2), ("minimax-m3", 3)):
        for index in range(count):
            db_session.add(
                LLMCall(
                    model=model,
                    task_key="control_extract",
                    prompt_hash=f"{model}-{index}",
                    tokens_in=100,
                    tokens_out=50,
                    cost=0.0,
                    latency_ms=10,
                    ruleset=RulesetName.GENERATION,
                    status="ok",
                    cost_unknown=model == "minimax-m3",
                )
            )
    await db_session.flush()

    assert await budget_module.uncosted_calls(db_session) == 3
