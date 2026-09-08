import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import AppSetting, LLMCall, LLMProviderConfig

logger = logging.getLogger(__name__)

WARN_RATIO = 0.8


class BudgetExceeded(Exception):
    pass


async def month_to_date_cost(
    session: AsyncSession, *, provider_config_id: int | None = None
) -> float:
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.coalesce(func.sum(LLMCall.cost), 0.0)).where(LLMCall.at >= start)
    if provider_config_id is not None:
        stmt = stmt.where(LLMCall.provider_config_id == provider_config_id)
    total = await session.scalar(stmt)
    return float(total or 0.0)


async def _budget(session: AsyncSession) -> float | None:
    setting = await session.get(AppSetting, "monthly_budget_usd")
    if setting is None:
        return None
    value = setting.value.get("value")
    return float(value) if value else None


def _enforce(scope: str, budget: float, spent: float, *, interactive: bool) -> None:
    """spec §9：达 80% 告警；达 100% 暂停批量任务，但保留交互式任务。"""
    if spent >= budget:
        if not interactive:
            raise BudgetExceeded(
                f"{scope}本月 AI 调用已达预算上限"
                f"（{spent:.2f} / {budget:.2f} USD），批量任务已暂停"
            )
        logger.warning("%s预算已用尽但放行交互式任务: %.2f / %.2f USD", scope, spent, budget)
    elif spent >= budget * WARN_RATIO:
        logger.warning(
            "%sAI 调用已达预算 %.0f%%: %.2f / %.2f USD",
            scope, spent / budget * 100, spent, budget,
        )


async def check(
    session: AsyncSession,
    *,
    interactive: bool,
    provider: LLMProviderConfig | None = None,
) -> None:
    """全局预算和 provider 级预算都要过，任一超标即拦。

    provider 级预算原本是个只存不看的死字段——设置页把它显示成一个开关，
    实际却从不生效，这比没有更糟。
    """
    global_budget = await _budget(session)
    if global_budget is not None and global_budget > 0:
        _enforce(
            "",
            global_budget,
            await month_to_date_cost(session),
            interactive=interactive,
        )

    if provider is not None and provider.monthly_budget and provider.monthly_budget > 0:
        _enforce(
            f"provider「{provider.name}」",
            float(provider.monthly_budget),
            await month_to_date_cost(session, provider_config_id=provider.id),
            interactive=interactive,
        )
