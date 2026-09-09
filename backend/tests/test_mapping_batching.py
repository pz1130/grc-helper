from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.mapping.batching import (
    MAX_CONTROL_CONTEXT_CHARS,
    build_batches,
    render_controls,
    render_items,
)


def item(id, code, level, title="t", description="d"):
    return SimpleNamespace(id=id, code=code, level=level, title=title, description=description)


def test_each_top_level_subtree_becomes_its_own_batch():
    items = [
        item(1, "PR", 1), item(2, "PR.AA", 2), item(3, "PR.AA-01", 3),
        item(4, "DE", 1), item(5, "DE.CM", 2),
    ]
    batches = build_batches(items)
    assert [[i.code for i in batch.items] for batch in batches] == [
        ["PR", "PR.AA", "PR.AA-01"], ["DE", "DE.CM"]]
    assert batches[0].section == "PR"


def test_an_oversized_subtree_splits_without_splitting_an_item():
    big = "x" * 5000
    items = [item(1, "AC", 1)] + [
        item(number, f"AC-{number}", 2, description=big) for number in range(2, 8)]
    batches = build_batches(items, max_chars=12000)
    assert len(batches) > 1
    assert sum(len(batch.items) for batch in batches) == len(items)
    assert all(batch.items for batch in batches)


def test_a_single_oversized_item_stays_intact_in_its_own_batch():
    items = [item(1, "AC", 1, description="x" * 40000)]
    batches = build_batches(items, max_chars=12000)
    assert len(batches) == 1 and len(batches[0].items) == 1


def test_render_items_exposes_id_code_and_description():
    text = render_items(build_batches([item(1, "PR.AA-01", 1, "Ident", "Body text.")])[0])
    assert "[framework_item_id=1]" in text
    assert "PR.AA-01" in text and "Ident" in text and "Body text." in text


def test_render_controls_exposes_id_and_statement():
    controls = [SimpleNamespace(id=9, code="C-0009", title="Dual approval",
                                statement="Two approvers required.")]
    text = render_controls(controls)
    assert "[control_id=9]" in text
    assert "C-0009" in text and "Two approvers required." in text


def test_control_context_over_the_hard_limit_fails_loudly():
    controls = [
        SimpleNamespace(id=number, code=f"C-{number:04d}", title="t", statement="x" * 1000)
        for number in range(1, 200)
    ]
    with pytest.raises(AppError) as excinfo:
        render_controls(controls)
    assert str(MAX_CONTROL_CONTEXT_CHARS) in str(excinfo.value)
    assert "199" in str(excinfo.value)


def test_empty_input_produces_no_batches():
    assert build_batches([]) == []
