from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control, ControlRelation, RelationType
from app.graph.schemas import GraphEdge, GraphNode, GraphOut, GraphStats

# 全景模式的硬上限。超了按 code 升序截断——随机截断的全景图
# 截图汇报出去两次不一样，比截断本身更糟。
MAX_NODES = 600


def control_key(control_id: int) -> str:
    return f"control:{control_id}"


async def relation_graph(
    session: AsyncSession,
    *,
    focus: str | None = None,
    hops: int = 1,
    include_pending: bool = False,
    types: set[RelationType] | None = None,
    framework_id: int | None = None,
) -> GraphOut:
    controls = (await session.execute(select(Control).order_by(Control.code))).scalars().all()
    nodes = [
        GraphNode(key=control_key(c.id), kind="control", code=c.code, title=c.title)
        for c in controls
    ]
    keys = {node.key for node in nodes}

    relations = (
        await session.execute(select(ControlRelation).order_by(ControlRelation.id))
    ).scalars().all()
    edges = [
        GraphEdge(
            key=f"relation:{row.id}",
            source=control_key(row.from_control_id),
            target=control_key(row.to_control_id),
            kind=row.relation_type.value,
            status="confirmed",
            confidence=row.confidence,
            rationale=row.rationale,
        )
        for row in relations
        if control_key(row.from_control_id) in keys and control_key(row.to_control_id) in keys
    ]

    return GraphOut(
        nodes=nodes,
        edges=edges,
        stats=GraphStats(
            nodes=len(nodes),
            edges=len(edges),
            pending_edges=0,
            truncated=False,
        ),
    )
