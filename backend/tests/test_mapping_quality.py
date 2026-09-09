"""Opt-in M5 calibration against the application database: make mapping-eval."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

OLIR = Path(__file__).parent / "fixtures" / "olir_csf_800-53.json"
TARGET_CITATION_PASS_RATE = 0.90
CSF_KEY = "nist-csf-2.0"
SP_KEY = "nist-800-53-r5"


@pytest.mark.skipif(
    os.environ.get("RUN_MAPPING_EVAL") != "1",
    reason="需显式开启真实模型标定，见 make mapping-eval",
)
@pytest.mark.asyncio
async def test_mapping_quality_calibration(capsys: Any) -> None:
    import app.models  # noqa: F401
    from app.controls.models import Control
    from app.frameworks.models import Framework, FrameworkItem
    from app.llm.routing import resolve
    from app.mapping.tasks import run_mapping
    from app.review.models import Proposal, ProposalKind

    app_url = os.environ.get("APP_DATABASE_URL")
    assert app_url, "APP_DATABASE_URL 必须显式指定应用库；不能使用测试库"
    assert app_url != os.environ.get("TEST_DATABASE_URL"), "标定不能打测试库"

    engine = create_async_engine(app_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    olir = json.loads(OLIR.read_text(encoding="utf-8"))
    expected = {pair["csf"]: set(pair["controls"]) for pair in olir["pairs"]}

    try:
        async with factory() as session:
            provider, _ = await resolve(session, "framework_mapping")
            controls = list(await session.scalars(select(Control)))
            assert controls, "控制点库为空；请先在确认队列中确认控制点"

            frameworks = {}
            for key in (CSF_KEY, SP_KEY):
                framework = await session.scalar(select(Framework).where(Framework.key == key))
                assert framework is not None, f"缺少框架 {key}；请先 make seed-frameworks"
                frameworks[key] = framework

            run_key = f"mapping-calibration:{uuid4()}"
            summaries, proposals_by_key = {}, {}
            for key, framework in frameworks.items():
                summary = await run_mapping(session, framework.id, run_key=run_key)
                await session.commit()
                summaries[key] = summary
                proposals_by_key[key] = list(await session.scalars(
                    select(Proposal).where(
                        Proposal.id.in_(summary["proposal_ids"]),
                        Proposal.kind == ProposalKind.MAPPING,
                    )
                ))

            codes: dict[int, str] = {
                item.id: item.code
                for item in await session.scalars(
                    select(FrameworkItem).where(
                        FrameworkItem.framework_id.in_([framework.id for framework in frameworks.values()])
                    )
                )
            }

            csf_by_control: dict[int, set[str]] = {}
            sp_by_control: dict[int, set[str]] = {}
            for key, bucket in ((CSF_KEY, csf_by_control), (SP_KEY, sp_by_control)):
                for proposal in proposals_by_key[key]:
                    control_id = proposal.payload["control_id"]
                    bucket.setdefault(control_id, set()).add(
                        codes[proposal.payload["framework_item_id"]]
                    )

            agree = total = 0
            disagreements: list[dict[str, Any]] = []
            for control_id, csf_codes in csf_by_control.items():
                sp_codes = sp_by_control.get(control_id, set())
                if not sp_codes:
                    continue
                for csf_code in csf_codes:
                    reference = expected.get(csf_code)
                    if not reference:
                        continue
                    total += 1
                    roots = {code.split("(")[0] for code in sp_codes}
                    if roots & reference:
                        agree += 1
                    else:
                        disagreements.append({
                            "control_id": control_id,
                            "csf": csf_code,
                            "proposed_800_53": sorted(roots),
                            "olir_expects": sorted(reference),
                        })

            batches = sum(summary["batches"] for summary in summaries.values())
            rejected = sum(summary["rejected"] for summary in summaries.values())
            pass_rate = 1 - rejected / batches if batches else 0.0
            consistency = agree / total if total else None
            report = {
                "model": provider.model,
                "controls": len(controls),
                "batches": batches,
                "rejected": rejected,
                "batch_validation_pass_rate": pass_rate,
                "olir_comparable_pairs": total,
                "olir_consistency": consistency,
                "proposals": {key: len(value) for key, value in proposals_by_key.items()},
                "disagreements": disagreements[:50],
                "note": "首轮为标定运行，OLIR 一致率不作判定",
            }
            if report_path := os.environ.get("MAPPING_REPORT_PATH"):
                Path(report_path).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            with capsys.disabled():
                for key, summary in summaries.items():
                    print(f"{key}: {summary['proposals']} mappings, rejected "
                          f"{summary['rejected']}/{summary['batches']}")
                print(f"Batch validation pass = {pass_rate:.2f}")
                if consistency is None:
                    print("OLIR consistency = N/A（没有可比对的配对）")
                else:
                    print(f"OLIR consistency = {consistency:.2f} "
                          f"({agree}/{total} comparable pairs) — 标定值，不作判定")
                print("Gap sanity: pending human review")

            assert pass_rate >= TARGET_CITATION_PASS_RATE, (
                f"批次校验通过率 {pass_rate:.2f} < {TARGET_CITATION_PASS_RATE}"
            )
    finally:
        await engine.dispose()
