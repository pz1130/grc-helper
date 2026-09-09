"""种子文件必须始终能通过导入校验——不写库，只解析。"""

import csv
from pathlib import Path

import pytest

from app.frameworks.template import parse_rows

SEEDS = Path(__file__).resolve().parents[1] / "seeds"


def _load(name: str) -> tuple[list[str], list[list[str]]]:
    text = (SEEDS / name).read_text(encoding="utf-8-sig")
    reader = list(csv.reader(text.splitlines()))
    return reader[0], reader[1:]


@pytest.mark.parametrize("name,minimum", [
    ("nist-csf-2.0.csv", 100),
    ("nist-800-53-r5.csv", 1000),
])
def test_seed_passes_template_validation(name, minimum):
    headers, rows = _load(name)
    parsed, report = parse_rows(headers, rows)
    assert report == [], report[:5]
    assert len(parsed) >= minimum


def test_800_53_marks_controls_as_requirements_and_carries_baselines():
    headers, rows = _load("nist-800-53-r5.csv")
    parsed, _ = parse_rows(headers, rows)
    controls = [row for row in parsed if row.attributes]
    assert controls, "800-53 控制项必须带 attributes"
    assert all(row.attributes.get("is_requirement") is True for row in controls)
    assert any("moderate" in ((row.attributes or {}).get("baselines") or []) for row in parsed)


def test_csf_leaves_requirement_flag_to_the_default_rule():
    headers, rows = _load("nist-csf-2.0.csv")
    parsed, _ = parse_rows(headers, rows)
    assert all(row.attributes is None for row in parsed)
