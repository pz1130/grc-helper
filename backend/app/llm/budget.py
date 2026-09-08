import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import AppSetting, LLMCall

logger = logging.getLogger(__name__)

WARN_RATIO = 0.8


class BudgetExceeded(Exception):
    pass


async def month_to_date_cost(session: AsyncSession) -> float:
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = await session.scalar(
        select(func.coalesce(func.sum(LLMCall.cost), 0.0)).where(LLMCall.at >= start)
    )
    return float(total or 0.0)


async def _budget(session: AsyncSession) -> float | None:
    setting = await session.get(AppSetting, "monthly_budget_usd")
    if setting is None:
        return None
    value = setting.value.get("value")
    return float(value) if value else None


async def check(session: AsyncSession, *, interactive: bool) -> None:
    """spec §9：达 80% 告警；达 100% 暂停批量任务，但保留交互式任务。"""
    budget = await _budget(session)
    if budget is None or budget <= 0:
        return

    spent = await month_to_date_cost(session)
    if spent >= budget:
        if not interactive:
            raise BudgetExceeded(
                f"本月 AI 调用已达预算上限（{spent:.2f} / {budget:.2f} USD），批量任务已暂停"
            )
        logger.warning("预算已用尽但放行交互式任务: %.2f / %.2f USD", spent, budget)
    elif spent >= budget * WARN_RATIO:
        logger.warning("AI 调用已达预算 %.0f%%: %.2f / %.2f USD", spent / budget * 100, spent, budget)
