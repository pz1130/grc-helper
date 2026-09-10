"""确认队列列表页的查询预算：往返次数不得随提案条数增长。

M5 留下的已知欠账——「`GET /api/proposals` 的 N+1（映射提案每条 3 次查询）」。
412 条待审映射提案下那是 1200 多次往返，而这一页正是要被人反复翻的那一页。

**这个测试量得到什么、量不到什么。** 测试夹具让 API 与建数据共用同一个
session，所以框架项与控制点在身份映射里，旧代码的 `session.get()` 在这里
本来就不会发查询——真实请求里 session 是全新的，那三次里的两次才会真的
往返。因此本测试可靠覆盖的是 OCR 标记那一路（`session.scalar`，从不走缓存）。
改回逐条查时它确实会失败：23 条 29 次 / 3 条 9 次。
"""

from typing import Self

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.controls.models import Control
from app.frameworks.models import Framework, FrameworkItem
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.review.models import Proposal, ProposalKind, ProposalStatus


class _Counter:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.n += 1

    def __enter__(self) -> Self:
        event.listen(Engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc) -> None:
        event.remove(Engine, "before_cursor_execute", self)


async def _framework(db_session, how_many: int, tag: str) -> list[FrameworkItem]:
    framework = Framework(key=f"f-{tag}", name_zh="框架", name_en="Framework", version="1")
    db_session.add(framework)
    await db_session.flush()
    items = [
        FrameworkItem(framework_id=framework.id, code=f"AC-{tag}-{n}", title=f"Item {n}",
                      description=f"Requirement text {n}.", level=1, order_index=n)
        for n in range(how_many)
    ]
    db_session.add_all(items)
    await db_session.flush()
    return items


async def _mapping_proposals(db_session, how_many: int, tag: str = "a") -> None:
    """每条提案都指向**不同**的控制点与框架项——同一个会被身份映射缓存掉，测不出 N+1。"""
    items = await _framework(db_session, how_many, tag)
    controls = [
        Control(code=f"C-{tag}-{n:04d}", title=f"Control {n}", statement=f"Statement {n}.")
        for n in range(how_many)
    ]
    db_session.add_all(controls)
    await db_session.flush()
    db_session.add_all([
        Proposal(
            kind=ProposalKind.MAPPING, status=ProposalStatus.PENDING, confidence=0.7,
            payload={
                "control_id": control.id, "framework_item_id": item.id,
                "strength": "partial", "framework_item_quote": f"Requirement text {n}.",
                "rationale": "because", "confidence": 0.7,
            },
            citations=[],
        )
        for n, (control, item) in enumerate(zip(controls, items, strict=True))
    ])
    await db_session.flush()


async def _auth(client, db_session) -> dict[str, str]:
    db_session.add(User(email="lead@example.com", name="Lead", role=Role.GRC_LEAD,
                        password_hash=hash_password("pw123456")))
    await db_session.flush()
    resp = await client.post(
        "/api/auth/login", json={"email": "lead@example.com", "password": "pw123456"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_listing_cost_does_not_grow_with_the_number_of_proposals(client, db_session):
    headers = await _auth(client, db_session)

    await _mapping_proposals(db_session, 3, tag="few")
    with _Counter() as few:
        small = await client.get("/api/proposals?kind=mapping&limit=200", headers=headers)
    assert len(small.json()) == 3

    await _mapping_proposals(db_session, 20, tag="many")
    with _Counter() as many:
        large = await client.get("/api/proposals?kind=mapping&limit=200", headers=headers)
    assert len(large.json()) == 23

    assert many.n == few.n, (
        f"23 条提案用了 {many.n} 次查询，3 条用了 {few.n} 次——查询数随条数增长即为 N+1"
    )
    print(f"\n列表页固定 {many.n} 次查询（3 条与 23 条相同）")


@pytest.mark.asyncio
async def test_the_listing_still_carries_full_mapping_context(client, db_session):
    """批量取数不能把旁路数据取丢了。"""
    headers = await _auth(client, db_session)
    await _mapping_proposals(db_session, 4)

    body = (await client.get("/api/proposals?kind=mapping&limit=200", headers=headers)).json()
    assert len(body) == 4
    for row in body:
        context = row["mapping_context"]
        assert context["framework_item"]["code"].startswith("AC-")
        assert context["control"]["code"].startswith("C-")
        assert context["control"]["statement"]
        assert row["bulk_acceptable"] is False      # 映射提案永远不可批量接受
        assert row["ocr_quality_flag"] is False
