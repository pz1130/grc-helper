import pytest
from sqlalchemy import select

from app.clauses.models import EMBEDDING_DIM, Clause
from app.controls.models import Control, ControlSource, SourceRelation
from app.ingest.models import DocStatus, DocType, Document
from app.relations.clustering import (
    duplicate_pairs,
    section_clusters,
    split_cluster,
)
from app.relations.models import ControlEmbedding


def _vector(seed: float) -> list[float]:
    """构造方向可控的单位向量：seed 越接近，余弦距离越小。"""
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0
    vector[1] = seed
    return vector


def test_split_cluster_keeps_overlap_so_the_seam_is_not_cut():
    chunks = split_cluster(list(range(1, 8)), max_size=4, overlap=2)
    assert chunks == [[1, 2, 3, 4], [3, 4, 5, 6], [5, 6, 7]]


def test_split_cluster_leaves_small_clusters_alone():
    assert split_cluster([1, 2, 3], max_size=4, overlap=2) == [[1, 2, 3]]


def test_split_cluster_rejects_an_overlap_that_cannot_advance():
    with pytest.raises(ValueError):
        split_cluster([1, 2, 3, 4, 5], max_size=3, overlap=3)


async def _seed_similar(db_session):
    near = [Control(code=f"C-{n:04d}", title=f"t{n}", statement="s") for n in (1, 2)]
    far = Control(code="C-0003", title="t3", statement="s")
    db_session.add_all([*near, far])
    await db_session.flush()
    db_session.add_all([
        ControlEmbedding(control_id=near[0].id, embedding=_vector(0.01),
                         embedding_model="embo-01"),
        ControlEmbedding(control_id=near[1].id, embedding=_vector(0.02),
                         embedding_model="embo-01"),
        ControlEmbedding(control_id=far.id, embedding=_vector(9.0),
                         embedding_model="embo-01"),
    ])
    await db_session.flush()
    return near, far


@pytest.mark.asyncio
async def test_duplicate_pairs_returns_similar_pairs_once_and_ordered(db_session):
    near, far = await _seed_similar(db_session)
    pairs = await duplicate_pairs(db_session, top_k=8, min_similarity=0.9)

    assert [(p.low, p.high) for p in pairs] == [(near[0].id, near[1].id)], \
        "同一对不能出现两次，且 low < high"
    assert far.id not in {p.low for p in pairs} | {p.high for p in pairs}


@pytest.mark.asyncio
async def test_a_high_threshold_filters_everything_out(db_session):
    await _seed_similar(db_session)
    assert await duplicate_pairs(db_session, top_k=8, min_similarity=0.999999) == []


@pytest.mark.asyncio
async def test_controls_without_an_embedding_are_skipped(db_session):
    db_session.add(Control(code="C-0009", title="t", statement="s"))
    await db_session.flush()
    assert await duplicate_pairs(db_session) == []


async def _seed_sections(db_session):
    doc = Document(title="P", doc_type=DocType.PROCEDURE, file_hash="a" * 64,
                   file_path="/x.pdf", original_filename="x.pdf", status=DocStatus.ACTIVE)
    db_session.add(doc)
    await db_session.flush()
    made = []
    for index, (path, code) in enumerate([
        ("Change Management › Approval", "C-0001"),
        ("Change Management › Approval", "C-0002"),
        ("Change Management › Implementation", "C-0003"),
        ("Roles", "C-0004"),
    ]):
        clause = Clause(document_id=doc.id, number=str(index), heading="H",
                        heading_path=path, citation_label=str(index),
                        text="body", order_index=index, level=2)
        control = Control(code=code, title=code, statement="s")
        db_session.add_all([clause, control])
        await db_session.flush()
        db_session.add(ControlSource(control_id=control.id, clause_id=clause.id,
                                     relation=SourceRelation.DEFINES))
        made.append(control)
    await db_session.flush()
    return made


@pytest.mark.asyncio
async def test_section_clusters_group_by_document_and_top_heading(db_session):
    made = await _seed_sections(db_session)
    clusters = await section_clusters(db_session)

    grouped = {c.label: set(c.control_ids) for c in clusters}
    change = next(ids for label, ids in grouped.items() if "Change Management" in label)
    assert change == {made[0].id, made[1].id, made[2].id}, "顶层标题相同即同簇"
    # Roles 只有一个控制点，section_clusters 会丢掉它；这里只确认它没有并入 Change 簇。
    assert made[3].id not in change, "不同顶层标题不得并入同簇"


@pytest.mark.asyncio
async def test_a_single_control_section_is_dropped(db_session):
    """一个控制点组不成对，没有关系可推。"""
    made = await _seed_sections(db_session)
    clusters = await section_clusters(db_session)
    assert all(len(c.control_ids) >= 2 for c in clusters)
    assert made[3].id not in {i for c in clusters for i in c.control_ids}


@pytest.mark.asyncio
async def test_an_oversized_section_is_split_with_overlap(db_session):
    doc = Document(title="Big", doc_type=DocType.PROCEDURE, file_hash="b" * 64,
                   file_path="/y.pdf", original_filename="y.pdf", status=DocStatus.ACTIVE)
    db_session.add(doc)
    await db_session.flush()
    for index in range(10):
        clause = Clause(document_id=doc.id, number=str(index), heading="H",
                        heading_path="Section", citation_label=str(index),
                        text="body", order_index=index, level=2)
        control = Control(code=f"B-{index:04d}", title="t", statement="s")
        db_session.add_all([clause, control])
        await db_session.flush()
        db_session.add(ControlSource(control_id=control.id, clause_id=clause.id,
                                     relation=SourceRelation.DEFINES))
    await db_session.flush()

    clusters = await section_clusters(db_session, max_size=4, overlap=2)
    sizes = [len(c.control_ids) for c in clusters]
    assert max(sizes) <= 4
    assert len(clusters) > 1
    assert len({i for c in clusters for i in c.control_ids}) == 10, "切分不得丢条目"
