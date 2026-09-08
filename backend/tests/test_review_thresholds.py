import pytest


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_invalid_confidence_never_bulk_accepts(confidence):
    assert not bulk_acceptable(_proposal(confidence), Thresholds(0.9, 0.6), ocr_flag=False)


def test_inverted_thresholds_fail_closed():
    assert not bulk_acceptable(_proposal(1), Thresholds(0.5, 0.9), ocr_flag=False)

from app.llm.models import AppSetting
from app.review.models import Proposal, ProposalKind
from app.review.thresholds import Thresholds, bulk_acceptable, load

DEFAULTS = Thresholds(auto_accept=0.90, force_manual=0.60)


def _proposal(confidence: float | None) -> Proposal:
    return Proposal(
        kind=ProposalKind.CONTROL_EXTRACT, payload={}, citations=[], confidence=confidence
    )


@pytest.mark.asyncio
async def test_load_reads_the_seeded_settings(db_session):
    """0004 迁移种了 0.90 / 0.60。"""
    thresholds = await load(db_session)
    assert thresholds.auto_accept == pytest.approx(0.90)
    assert thresholds.force_manual == pytest.approx(0.60)


@pytest.mark.asyncio
async def test_load_reflects_admin_changes(db_session):
    setting = await db_session.get(AppSetting, "auto_accept_threshold")
    setting.value = {"value": 0.95}
    await db_session.flush()

    assert (await load(db_session)).auto_accept == pytest.approx(0.95)


def test_high_confidence_can_be_bulk_accepted():
    assert bulk_acceptable(_proposal(0.95), DEFAULTS, ocr_flag=False) is True


def test_confidence_exactly_at_the_threshold_is_acceptable():
    assert bulk_acceptable(_proposal(0.90), DEFAULTS, ocr_flag=False) is True


def test_middle_confidence_is_not_bulk_acceptable():
    assert bulk_acceptable(_proposal(0.75), DEFAULTS, ocr_flag=False) is False


def test_low_confidence_is_not_bulk_acceptable():
    assert bulk_acceptable(_proposal(0.40), DEFAULTS, ocr_flag=False) is False


def test_missing_confidence_is_treated_conservatively():
    assert bulk_acceptable(_proposal(None), DEFAULTS, ocr_flag=False) is False


def test_ocr_suspect_document_forbids_bulk_regardless_of_confidence():
    """spec §9：OCR 存疑的文档，其衍生提案一律逐条确认，无视阈值。"""
    assert bulk_acceptable(_proposal(0.99), DEFAULTS, ocr_flag=True) is False
