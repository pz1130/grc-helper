"""按语料自动标定 duplicates 通道的相似度阈值。

**为什么可以自动**：任何一份制度语料里，只要有把同一段要求复制进两份文档的情况，
就会产生 `statement` 逐字相同的控制点对。它们**必然是重复**，而且 SQL 一行就能
查出来——这是一组不需要人工标注、每份语料自带的正样本。

标定就是量这组正样本的相似度，把阈值定在最低的那个之下留一点余量。手工做过一次：
某语料的三对已知重复落在 0.942 / 0.969 / 0.979，阈值定 0.90。

**语料里没有逐字重复怎么办**：不写、不猜，如实报告「无法标定」。沿用别人语料标出来
的阈值比没有阈值更糟——它看起来像个结论。
"""

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control
from app.relations.models import ControlEmbedding

# 阈值比最低的已知正样本再低这么多：正样本只是语料里恰好逐字重复的那些，
# 真实的重复对会比它们更「不像」，不留余量必然漏。
MARGIN = 0.04
MIN_GROUND_TRUTH_PAIRS = 3


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class Calibration:
    pairs: list[tuple[str, str, float]]
    recommended: float | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ground_truth_pairs": [
                {"a": a, "b": b, "similarity": round(s, 4)} for a, b, s in self.pairs
            ],
            "recommended_min_similarity": self.recommended,
            "reason": self.reason,
        }


async def identical_statement_pairs(session: AsyncSession) -> list[tuple[int, int]]:
    """statement 逐字相同的控制点对——复制粘贴留下的免费正样本。"""
    rows = await session.execute(
        select(Control.statement, func.array_agg(Control.id).label("ids"))
        .where(Control.statement.is_not(None), func.length(Control.statement) > 40)
        .group_by(Control.statement)
        .having(func.count() > 1)
    )
    pairs: list[tuple[int, int]] = []
    for _, ids in rows:
        ordered = sorted(ids)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                pairs.append((a, b))
    return pairs


async def calibrate(session: AsyncSession) -> Calibration:
    pairs = await identical_statement_pairs(session)
    if len(pairs) < MIN_GROUND_TRUTH_PAIRS:
        return Calibration(
            [], None,
            f"本语料只找到 {len(pairs)} 对 statement 逐字相同的控制点"
            f"（至少需要 {MIN_GROUND_TRUTH_PAIRS} 对），无法标定。"
            "duplicates 通道将沿用默认阈值，其结果仅供参考。",
        )

    wanted = {i for pair in pairs for i in pair}
    codes = {
        c.id: c.code
        for c in await session.scalars(select(Control).where(Control.id.in_(wanted)))
    }
    # 一次取回全部向量，在内存里两两算。逐对发 SQL 既是 N 次往返，
    # 两个别名不加连接条件还会被 SQLAlchemy 判成笛卡尔积。
    vectors = {
        row.control_id: row.embedding
        for row in await session.scalars(
            select(ControlEmbedding).where(
                ControlEmbedding.control_id.in_(wanted),
                ControlEmbedding.embedding.is_not(None),
            )
        )
    }

    scored: list[tuple[str, str, float]] = []
    for a, b in pairs:
        left, right = vectors.get(a), vectors.get(b)
        if left is None or right is None:
            continue  # 还没向量化，跳过而不是当成相似度 0——那会把阈值拉到地板
        scored.append((codes.get(a, str(a)), codes.get(b, str(b)), _cosine(left, right)))

    if len(scored) < MIN_GROUND_TRUTH_PAIRS:
        return Calibration(
            scored, None,
            f"{len(pairs)} 对正样本里只有 {len(scored)} 对已向量化，不足以标定。"
            "请先补算控制点向量再试。",
        )

    scored.sort(key=lambda row: row[2])
    lowest = scored[0][2]
    recommended = round(max(0.0, min(1.0, lowest - MARGIN)), 3)
    return Calibration(
        scored, recommended,
        f"{len(scored)} 对已知重复的相似度落在 {lowest:.3f}–{scored[-1][2]:.3f}，"
        f"阈值取最低值再留 {MARGIN} 余量。",
    )
