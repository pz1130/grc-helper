"""Opt-in M6 relation review against the application database: make relation-eval.

不设自动质量指标：关系对错是语义判断，没有 OLIR 那样的权威外部标尺。
M4 用词组召回、M5 用官方交叉映射，都是因为恰好存在可用基准；这里没有。
强造一个只会得到又一个测不了的闸门。
"""

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TARGET_CITATION_PASS_RATE = 0.90


@pytest.mark.skipif(
    os.environ.get("RUN_RELATION_EVAL") != "1",
    reason="需显式开启真实模型抽查，见 make relation-eval",
)
@pytest.mark.asyncio
async def test_relation_inference_produces_reviewable_output(capsys: Any) -> None:
    import app.models  # noqa: F401
    from app.controls.models import Control
    from app.llm.routing import resolve
    from app.relations.indexing import embed_pending
    from app.relations.tasks import run_inference
    from app.review.models import Proposal, ProposalKind

    app_url = os.environ.get("APP_DATABASE_URL")
    assert app_url, "APP_DATABASE_URL 必须显式指定应用库；不能使用测试库"
    assert app_url != os.environ.get("TEST_DATABASE_URL"), "抽查不能打测试库"

    engine = create_async_engine(app_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            provider, _ = await resolve(session, "relation_inference")
            controls = {c.id: c for c in await session.scalars(select(Control))}
            assert controls, "控制点库为空；请先在确认队列中确认控制点"

            indexed = await embed_pending(session)
            await session.commit()

            summary = await run_inference(session, run_key=f"relation-eval:{uuid4()}")
            await session.commit()

            proposals = list(await session.scalars(
                select(Proposal).where(
                    Proposal.id.in_(summary["proposal_ids"]),
                    Proposal.kind == ProposalKind.RELATION,
                )
            ))
            attempted = summary["attempted_batches"]
            pass_rate = (attempted - summary["rejected"]) / attempted if attempted else 0.0

            by_type: dict[str, list[dict[str, Any]]] = {}
            for proposal in proposals:
                payload = proposal.payload
                left = controls[payload["from_control_id"]]
                right = controls[payload["to_control_id"]]
                by_type.setdefault(payload["relation_type"], []).append({
                    "proposal_id": proposal.id,
                    "from": f"{left.code} {left.title}",
                    "to": f"{right.code} {right.title}",
                    "from_quote": payload["from_quote"],
                    "to_quote": payload["to_quote"],
                    "rationale": payload["rationale"],
                    "confidence": payload["confidence"],
                })

            report = {
                "model": provider.model,
                "controls": len(controls),
                "embedded": indexed["embedded"],
                "batches": summary["batches"],
                "rejected": summary["rejected"],
                "failed": summary["failed"],
                "dropped_relations": summary["dropped_relations"],
                "citation_pass_rate": pass_rate,
                "relations": {k: len(v) for k, v in by_type.items()},
                "samples": by_type,
                "precision": None,
                "precision_note": "需人工逐条判断关系是否成立；本脚本不推断该值",
            }
            if report_path := os.environ.get("RELATION_REPORT_PATH"):
                Path(report_path).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            with capsys.disabled():
                print(f"model={provider.model} controls={len(controls)} "
                      f"batches={summary['batches']}")
                print(f"闸 4 通过率 = {pass_rate:.2f}  "
                      f"（rejected {summary['rejected']} / failed {summary['failed']} / "
                      f"逐条丢弃 {summary['dropped_relations']}）")
                for relation_type, rows in by_type.items():
                    print(f"{relation_type}: {len(rows)} 条")
                print("precision: pending human review（不由脚本推断）")

            assert pass_rate >= TARGET_CITATION_PASS_RATE, (
                f"闸 4 通过率 {pass_rate:.2f} < {TARGET_CITATION_PASS_RATE}")
    finally:
        await engine.dispose()
