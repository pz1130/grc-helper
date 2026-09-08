"""置信度阈值（spec §7.4 D11）。

M1 把这两个值存进了 AppSetting，M4 是第一个消费者。
"""

from dataclasses import dataclass
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import AppSetting
from app.review.models import Proposal

_AUTO_ACCEPT_DEFAULT = 0.90
_FORCE_MANUAL_DEFAULT = 0.60


@dataclass(frozen=True)
class Thresholds:
    auto_accept: float
    force_manual: float


async def _value(session: AsyncSession, key: str, fallback: float) -> float:
    setting = await session.get(AppSetting, key)
    if setting is None:
        return fallback
    try:
        value = setting.value["value"]
        if isinstance(value, bool):
            return fallback
        result = float(value)
        return result if math.isfinite(result) and 0 <= result <= 1 else fallback
    except (KeyError, TypeError, ValueError):
        return fallback


async def load(session: AsyncSession) -> Thresholds:
    return Thresholds(
        auto_accept=await _value(session, "auto_accept_threshold", _AUTO_ACCEPT_DEFAULT),
        force_manual=await _value(session, "force_manual_threshold", _FORCE_MANUAL_DEFAULT),
    )


def bulk_acceptable(proposal: Proposal, thresholds: Thresholds, *, ocr_flag: bool) -> bool:
    """能否被批量接受。

    OCR 存疑的文档一律禁止批量，无视置信度（spec §9）——OCR 出错时模型看到的
    本来就是乱码，它对乱码的高置信度毫无意义。
    """
    if ocr_flag:
        return False
    if proposal.confidence is None:
        return False   # 没有置信度就保守处理
    confidence = proposal.confidence
    return (
        not isinstance(confidence, bool)
        and math.isfinite(confidence)
        and 0 <= confidence <= 1
        and 0 <= thresholds.force_manual <= thresholds.auto_accept <= 1
        and confidence >= thresholds.auto_accept
        and confidence >= thresholds.force_manual
    )

