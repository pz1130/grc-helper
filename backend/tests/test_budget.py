import pytest

from app.llm.budget import BudgetExceeded, check, month_to_date_cost
from app.llm.models import AppSetting, LLMCall, RulesetName


async def _spend(db_session, amount: float) -> None:
    db_session.add(
        LLMCall(
            model="claude-opus-5",
            task_key="control_extract",
            prompt_hash="h",
            cost=amount,
            ruleset=RulesetName.GENERATION,
            status="ok",
        )
    )
    await db_session.flush()


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
