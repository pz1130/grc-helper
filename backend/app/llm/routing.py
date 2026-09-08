from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.llm.models import LLMProviderConfig, TaskRouting


class RoutingError(AppError):
    code = "routing_error"


async def resolve(session: AsyncSession, task_key: str) -> tuple[LLMProviderConfig, TaskRouting]:
    routing = await session.scalar(select(TaskRouting).where(TaskRouting.task_key == task_key))
    if routing is None:
        raise RoutingError(f"任务 {task_key} 尚未配置 provider，请到设置页配置")

    config = await session.get(LLMProviderConfig, routing.provider_config_id)
    if config is None or not config.enabled:
        raise RoutingError(f"任务 {task_key} 绑定的 provider 不可用")
    return config, routing


async def fallback_provider(session: AsyncSession) -> LLMProviderConfig | None:
    return await session.scalar(
        select(LLMProviderConfig).where(
            LLMProviderConfig.is_fallback.is_(True), LLMProviderConfig.enabled.is_(True)
        )
    )
