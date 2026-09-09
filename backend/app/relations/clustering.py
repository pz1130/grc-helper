"""双通道候选生成——全程无 AI，纯 SQL 与向量查询。

两条通道的批次形状不同，因为两种关系的拓扑不同：

- duplicates 是「一对」的属性，向量相似度天然产出对，按对批。
  不用连通分量分簇：相似度具传递性，容易把控制点连成一个巨型分量。
- depends_on 是流程属性（「先审批，后实施」），模型要看到整段顺序才判得准，
  按章节簇批。相似度对它无效——A 依赖 B 不意味着 A 像 B。
"""

from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.clauses.models import Clause
from app.controls.models import ControlSource
from app.relations.models import ControlEmbedding

TOP_K_NEIGHBOURS = 8
MIN_SIMILARITY = 0.75
MAX_CLUSTER_SIZE = 20
CLUSTER_OVERLAP = 3


class Pair(NamedTuple):
    low: int
    high: int
    similarity: float


@dataclass(frozen=True)
class Cluster:
    control_ids: list[int]
    label: str


def split_cluster(ids: list[int], *, max_size: int, overlap: int) -> list[list[int]]:
    """按顺序切分，相邻块保留重叠，避免切口处的依赖被切断。"""
    if max_size <= overlap:
        raise ValueError("overlap 必须小于 max_size，否则切分无法前进")
    if len(ids) <= max_size:
        return [list(ids)]
    step = max_size - overlap
    chunks = []
    for start in range(0, len(ids), step):
        chunk = ids[start : start + max_size]
        if chunk:
            chunks.append(chunk)
        if start + max_size >= len(ids):
            break
    return chunks


async def duplicate_pairs(
    session: AsyncSession,
    *,
    top_k: int = TOP_K_NEIGHBOURS,
    min_similarity: float = MIN_SIMILARITY,
) -> list[Pair]:
    """每个控制点取 top-k 近邻，过阈值后按 (low, high) 去重。"""
    rows = list(
        await session.scalars(
            select(ControlEmbedding).where(ControlEmbedding.embedding.is_not(None))
        )
    )
    other = aliased(ControlEmbedding)
    best: dict[tuple[int, int], float] = {}
    for row in rows:
        distance = other.embedding.cosine_distance(row.embedding)
        neighbours = await session.execute(
            select(other.control_id, distance.label("distance"))
            .where(other.embedding.is_not(None), other.control_id != row.control_id)
            .order_by(distance, other.control_id)
            .limit(top_k)
        )
        for control_id, raw in neighbours:
            similarity = 1.0 - float(raw)
            if similarity < min_similarity:
                continue
            key = (min(row.control_id, control_id), max(row.control_id, control_id))
            best[key] = max(best.get(key, 0.0), similarity)
    return [
        Pair(low, high, score)
        for (low, high), score in sorted(best.items(), key=lambda kv: -kv[1])
    ]


async def section_clusters(
    session: AsyncSession,
    *,
    max_size: int = MAX_CLUSTER_SIZE,
    overlap: int = CLUSTER_OVERLAP,
) -> list[Cluster]:
    """按 (document_id, heading_path 顶层) 分簇，保持 order_index 顺序。"""
    rows = await session.execute(
        select(ControlSource.control_id, Clause.document_id, Clause.heading_path)
        .join(Clause, Clause.id == ControlSource.clause_id)
        .order_by(Clause.document_id, Clause.order_index, ControlSource.control_id)
    )
    grouped: dict[tuple[int, str], list[int]] = {}
    for control_id, document_id, heading_path in rows:
        top = (heading_path or "").split("›")[0].strip()
        bucket = grouped.setdefault((document_id, top), [])
        # 同一控制点可由同章节多条条款支撑，只保留一次且保持首次出现的顺序。
        if control_id not in bucket:
            bucket.append(control_id)

    clusters: list[Cluster] = []
    for (document_id, top), ids in grouped.items():
        # 一个控制点组不成对，没有关系可推。
        if len(ids) < 2:
            continue
        for position, chunk in enumerate(
            split_cluster(ids, max_size=max_size, overlap=overlap), start=1
        ):
            if len(chunk) < 2:
                continue
            label = f"doc{document_id}:{top}" + (f" #{position}" if position > 1 else "")
            clusters.append(Cluster(chunk, label))
    return clusters
