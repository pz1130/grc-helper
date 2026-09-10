"""按语料标定的参数与自动标定。

这些值依赖具体语料：MIN_SIMILARITY 是拿一份 136 个控制点的语料标出来的，
换一份文档集就不成立。写死在常量里意味着换客户要改代码，而且没人知道改成多少。
"""

import pytest
from sqlalchemy import select

from app.controls.models import Control
from app.llm.models import AppSetting
from app.relations import clustering, params
from app.relations.calibration import MARGIN, MIN_GROUND_TRUTH_PAIRS, calibrate
from app.relations.models import ControlEmbedding


def _vector(seed: float) -> list[float]:
    from app.clauses.models import EMBEDDING_DIM

    v = [0.0] * EMBEDDING_DIM
    v[0] = 1.0
    v[1] = seed
    return v


async def _set(db_session, name: str, value) -> None:
    db_session.add(AppSetting(key=params.PREFIX + name, value={"value": value}))
    await db_session.flush()


@pytest.mark.asyncio
async def test_defaults_are_the_module_constants(db_session):
    cfg = await params.load(db_session)
    assert cfg.min_similarity == clustering.MIN_SIMILARITY
    assert cfg.top_k == clustering.TOP_K_NEIGHBOURS
    assert cfg.max_batch_chars == clustering.MAX_BATCH_CHARS


@pytest.mark.asyncio
async def test_a_stored_value_overrides_the_default(db_session):
    await _set(db_session, "min_similarity", 0.82)
    assert (await params.load(db_session)).min_similarity == 0.82


@pytest.mark.asyncio
# NaN 不在列内：JSONB 存不了它，写入阶段就会被数据库拒绝。
# _value 里的 isfinite 仍然留着——它防的是别的来源，不是这条路径。
@pytest.mark.parametrize("bad", [1.5, -0.1, "abc", None, True])
async def test_an_unusable_value_falls_back_instead_of_breaking_the_run(db_session, bad):
    """配置坏了应当退回默认值，而不是让整轮推断崩在半路。"""
    await _set(db_session, "min_similarity", bad)
    assert (await params.load(db_session)).min_similarity == clustering.MIN_SIMILARITY


@pytest.mark.asyncio
async def test_overlap_not_smaller_than_cluster_size_falls_back(db_session):
    """两个值各自合法、组合起来会让 split_cluster 抛异常——只有配置项之间才有的失效。"""
    await _set(db_session, "max_cluster_size", 5)
    await _set(db_session, "cluster_overlap", 5)
    cfg = await params.load(db_session)
    assert cfg.cluster_overlap < cfg.max_cluster_size


async def _identical(db_session, codes: list[str], text: str, seeds: list[float]) -> None:
    rows = [Control(code=c, title=c, statement=text) for c in codes]
    db_session.add_all(rows)
    await db_session.flush()
    for control, seed in zip(rows, seeds, strict=True):
        db_session.add(ControlEmbedding(control_id=control.id, embedding=_vector(seed),
                                        embedding_model="embo-01", embedding_version="v2"))
    await db_session.flush()


@pytest.mark.asyncio
async def test_calibration_uses_byte_identical_statements_as_free_ground_truth(db_session):
    """复制粘贴产生的逐字相同控制点必然是重复——不需要人工标注的正样本。"""
    await _identical(db_session, ["C-1", "C-2", "C-3"],
                     "Exceptions to the policy must be justified and handled accordingly.",
                     [0.02, 0.05, 0.09])
    result = await calibrate(db_session)

    assert len(result.pairs) == 3          # 三条相同 → 三对
    assert result.recommended is not None
    lowest = min(s for _, _, s in result.pairs)
    assert result.recommended == pytest.approx(round(lowest - MARGIN, 3), abs=1e-6)
    assert result.recommended < lowest, "阈值必须低于最低的已知正样本，否则它自己都会被漏掉"


@pytest.mark.asyncio
async def test_calibration_refuses_when_the_corpus_has_no_ground_truth(db_session):
    """标不出来就不写——沿用别人语料的阈值比没有阈值更糟，它看起来像个结论。"""
    db_session.add_all([
        Control(code="C-9", title="a", statement="A" * 60),
        Control(code="C-8", title="b", statement="B" * 60),
    ])
    await db_session.flush()

    result = await calibrate(db_session)
    assert result.recommended is None
    assert str(MIN_GROUND_TRUTH_PAIRS) in result.reason


@pytest.mark.asyncio
async def test_calibration_does_not_treat_unembedded_pairs_as_dissimilar(db_session):
    """没向量化的对要跳过，不能当成相似度 0——那会把阈值拉到地板。"""
    rows = [Control(code=f"C-{n}", title="t", statement="X" * 80) for n in range(3)]
    db_session.add_all(rows)
    await db_session.flush()

    result = await calibrate(db_session)
    assert result.recommended is None
    assert "向量化" in result.reason


@pytest.mark.asyncio
async def test_calibrate_endpoint_writes_the_threshold_and_audits(client, db_session):
    from app.iam.models import AuditLog, User
    from app.iam.permissions import Role
    from app.iam.security import hash_password

    db_session.add(User(email="lead@example.com", name="L", role=Role.GRC_LEAD,
                        password_hash=hash_password("pw123456")))
    await db_session.flush()
    await _identical(db_session, ["C-1", "C-2", "C-3"], "Y" * 80, [0.02, 0.05, 0.09])
    token = (await client.post("/api/auth/login",
                               json={"email": "lead@example.com", "password": "pw123456"})
             ).json()["access_token"]

    body = (await client.post("/api/relations/calibrate",
                              headers={"Authorization": f"Bearer {token}"})).json()

    assert body["applied"] is True
    stored = await db_session.get(AppSetting, params.PREFIX + "min_similarity")
    assert stored.value["value"] == body["recommended_min_similarity"]
    actions = list(await db_session.scalars(select(AuditLog.action)))
    assert "relations.calibrate" in actions
