from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control, ControlRelation, ControlSource, RelationType
from app.errors import BadRequest
from app.graph.schemas import GraphEdge, GraphNode, GraphOut, GraphStats
from app.review.models import Proposal, ProposalKind, ProposalStatus

# 全景模式的硬上限。超了按 code 升序截断——随机截断的全景图
# 截图汇报出去两次不一样，比截断本身更糟。
MAX_NODES = 600


def control_key(control_id: int) -> str:
    return f"control:{control_id}"


def parse_focus(focus: str) -> tuple[str, int]:
    """`control:57` / `document:3` / `item:1172` → ("control", 57)。"""
    kind, _, raw = focus.partition(":")
    if kind not in {"control", "document", "item"} or not raw.isdigit():
        raise BadRequest("focus 需形如 control:57 / document:3 / item:1172")
    return kind, int(raw)


def _neighbourhood(seeds: set[str], edges: list[GraphEdge], hops: int) -> set[str]:
    """在合并后的边集上做 BFS。

    因此打开待确认边之后，原本 2 跳可达的点可能变 1 跳——这是对的，
    但也正因如此 stats 必须把两类边分开计数。
    """
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)
        adjacency.setdefault(edge.target, set()).add(edge.source)

    reached = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        nxt: set[str] = set()
        for key in frontier:
            nxt |= adjacency.get(key, set()) - reached
        if not nxt:
            break
        reached |= nxt
        frontier = nxt
    return reached


def _pair_key(source: str, target: str, kind: str) -> tuple[str, str, str]:
    """duplicates 无方向，正反两条是同一条；depends_on 有方向，不可混。"""
    if kind == RelationType.DUPLICATES.value:
        first, second = sorted((source, target))
        return first, second, kind
    return source, target, kind


async def _pending_relation_edges(
    session: AsyncSession, keys: set[str], types: set[RelationType] | None
) -> list[GraphEdge]:
    rows = (
        await session.execute(
            select(Proposal)
            .where(
                Proposal.kind == ProposalKind.RELATION,
                Proposal.status == ProposalStatus.PENDING,
            )
            .order_by(Proposal.id)
        )
    ).scalars().all()

    edges: list[GraphEdge] = []
    for row in rows:
        payload = row.payload or {}
        source = control_key(payload.get("from_control_id", 0))
        target = control_key(payload.get("to_control_id", 0))
        kind = payload.get("relation_type", "")
        if source not in keys or target not in keys:
            continue
        if types is not None and kind not in {t.value for t in types}:
            continue
        edges.append(
            GraphEdge(
                key=f"proposal:{row.id}",
                source=source,
                target=target,
                kind=kind,
                status="pending",
                confidence=payload.get("confidence", row.confidence),
                rationale=payload.get("rationale", ""),
                proposal_id=row.id,
            )
        )
    return edges


async def _relation_seeds(session: AsyncSession, kind: str, target_id: int) -> set[str]:
    if kind == "control":
        return {control_key(target_id)}
    if kind == "document":
        rows = (
            await session.execute(
                select(ControlSource.control_id)
                .join(Clause, Clause.id == ControlSource.clause_id)
                .where(Clause.document_id == target_id)
            )
        ).scalars().all()
        return {control_key(control_id) for control_id in rows}
    raise BadRequest("关系图的 focus 只能是 control: 或 document:")


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

    if include_pending:
        seen = {_pair_key(e.source, e.target, e.kind) for e in edges}
        for edge in await _pending_relation_edges(session, keys, types):
            pair = _pair_key(edge.source, edge.target, edge.kind)
            if pair in seen:  # 已确认的赢，不画重影
                continue
            seen.add(pair)
            edges.append(edge)

    if focus is not None:
        kind, target_id = parse_focus(focus)
        seeds = await _relation_seeds(session, kind, target_id)
        reached = _neighbourhood(seeds, edges, hops)
        nodes = [node for node in nodes if node.key in reached]
        keys = {node.key for node in nodes}
        edges = [e for e in edges if e.source in keys and e.target in keys]

    pending_count: dict[str, int] = {}
    for edge in edges:
        if edge.status != "pending":
            continue
        pending_count[edge.source] = pending_count.get(edge.source, 0) + 1
        pending_count[edge.target] = pending_count.get(edge.target, 0) + 1
    for node in nodes:
        node.pending_edges = pending_count.get(node.key, 0)

    return GraphOut(
        nodes=nodes,
        edges=edges,
        stats=GraphStats(
            nodes=len(nodes),
            edges=len(edges),
            pending_edges=sum(1 for e in edges if e.status == "pending"),
            truncated=False,
        ),
    )
