"""Pure orchestration tests; no database connection or shared fixtures."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.errors import AppError
from app.llm.providers.base import ProviderError
from app.llm.runner import ValidatedResult
from app.llm.validation import ValidationFailure
from app.relations import tasks
from app.relations.clustering import Cluster, Pair
from app.worker import WorkerSettings


def relation(**overrides):
    return {
        "from_control_id": 1, "to_control_id": 2,
        "from_quote": "a", "to_quote": "b",
        "rationale": "because they overlap", "confidence": 0.8,
        **overrides,
    }


@pytest.fixture
def harness(monkeypatch):
    controls = [
        SimpleNamespace(id=1, code="C-0001", title="Approval", statement="a"),
        SimpleNamespace(id=2, code="C-0002", title="Implementation", statement="b"),
    ]
    call = SimpleNamespace(id=10, redaction_hits={"dictionary": 2})

    session = MagicMock()
    session.get = AsyncMock(return_value=call)
    session.scalars = AsyncMock(return_value=controls)
    session.scalar = AsyncMock(return_value=None)   # 无检查点
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    @asynccontextmanager
    async def savepoint():
        yield None

    session.begin_nested = savepoint

    monkeypatch.setattr(
        tasks, "duplicate_pairs", AsyncMock(return_value=[Pair(1, 2, 0.91)]))
    monkeypatch.setattr(
        tasks, "section_clusters", AsyncMock(return_value=[Cluster([1, 2], "doc1:Change")]))
    run = AsyncMock(return_value=ValidatedResult({"relations": [relation()]}, 0.9, 10))
    create = AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(id=21))
    monkeypatch.setattr(tasks, "run", run)
    monkeypatch.setattr(tasks.review_service, "create", create, raising=False)
    monkeypatch.setattr(
        tasks.RelationCitationValidator, "check", AsyncMock(return_value=None), raising=False)
    return SimpleNamespace(session=session, controls=controls, call=call,
                           run=run, create=create)


async def test_both_channels_run_and_each_fixes_its_relation_type(harness):
    summary = await tasks.run_inference(harness.session, run_key="t1")

    assert summary["batches"] == 2          # 一对批 + 一簇批
    assert summary["proposals"] == 2
    kinds = {call.kwargs["kind"].value for call in harness.create.await_args_list}
    assert kinds == {"relation"}
    types = {
        call.kwargs["payload"]["relation_type"]
        for call in harness.create.await_args_list
    }
    assert types == {"duplicates", "depends_on"}, "关系类型由通道决定，不由模型给出"


async def test_the_duplicate_prompt_differs_from_the_dependency_prompt(harness):
    await tasks.run_inference(harness.session)
    systems = {call.kwargs["system"] for call in harness.run.await_args_list}
    assert len(systems) == 2


async def test_a_rejected_batch_is_counted_not_silently_dropped(harness, monkeypatch):
    monkeypatch.setattr(
        tasks, "run", AsyncMock(side_effect=ValidationFailure("模型输出中没有找到合法的 JSON 对象")))
    summary = await tasks.run_inference(harness.session)
    assert summary["rejected"] == 2 and summary["proposals"] == 0


async def test_a_provider_error_fails_the_batch_without_killing_the_run(harness, monkeypatch):
    calls = {"n": 0}

    async def flaky(session, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("网络错误: ReadTimeout", retryable=True)
        return ValidatedResult({"relations": [relation()]}, 0.9, 10)

    monkeypatch.setattr(tasks, "run", AsyncMock(side_effect=flaky))
    summary = await tasks.run_inference(harness.session)
    assert summary["failed"] == 1
    assert summary["rejected"] == 0
    assert summary["completed_batches"] == 1


async def test_one_bad_citation_drops_only_that_relation(harness, monkeypatch):
    good, bad = relation(), relation(to_control_id=999)
    monkeypatch.setattr(
        tasks, "run",
        AsyncMock(return_value=ValidatedResult({"relations": [good, bad]}, 0.9, 10)))

    async def check(self, payload):
        bad_entries = [e for e in payload["relations"] if e["to_control_id"] != 2]
        return "控制点 999 不属于本批次" if bad_entries else None

    monkeypatch.setattr(tasks.RelationCitationValidator, "check", check)
    summary = await tasks.run_inference(harness.session)

    assert summary["dropped_relations"] == 2   # 两条通道各丢一条
    assert summary["rejected"] == 0


async def test_the_checkpoint_lock_is_released_before_the_model_call(harness, monkeypatch):
    order: list[str] = []
    original = harness.session.commit

    async def tracking_commit():
        order.append("commit")
        return await original()

    async def tracking_run(session, **kwargs):
        order.append("llm")
        return ValidatedResult({"relations": [relation()]}, 0.9, 10)

    harness.session.commit = AsyncMock(side_effect=tracking_commit)
    monkeypatch.setattr(tasks, "run", AsyncMock(side_effect=tracking_run))
    await tasks.run_inference(harness.session)

    assert order.index("commit") < order.index("llm"), (
        f"advisory 锁不得跨越 LLM 调用；实际顺序 {order}"
    )


async def test_an_empty_control_library_refuses_to_run(harness, monkeypatch):
    monkeypatch.setattr(tasks, "duplicate_pairs", AsyncMock(return_value=[]))
    monkeypatch.setattr(tasks, "section_clusters", AsyncMock(return_value=[]))
    harness.session.scalars = AsyncMock(return_value=[])
    with pytest.raises(AppError):
        await tasks.run_inference(harness.session)


def test_infer_relations_is_registered_with_a_two_hour_timeout():
    """ARQ 读 Function.timeout_s；挂在 coroutine 上的 timeout 属性是无效的。"""
    registered = next(
        f for f in WorkerSettings.functions if getattr(f, "name", None) == "infer_relations"
    )
    assert registered.timeout_s == 7200
    assert WorkerSettings.job_timeout == 900
