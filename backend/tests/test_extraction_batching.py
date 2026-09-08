import pytest

import app.models  # noqa: F401 — resolve Clause's Document relationship without database access
from app.clauses.models import Clause
from app.extraction.batching import MAX_BATCH_CHARS, build_batches, render


def clause(cid, level=1, text="Body", heading="Heading"):
    return Clause(id=cid, document_id=1, number=str(cid), citation_label=str(cid),
                  level=level, text=text, heading=heading, order_index=cid)


def test_section_children_stay_together():
    batches = build_batches([clause(1), clause(2, 2), clause(3, 3), clause(4)])
    assert [[c.id for c in b.clauses] for b in batches] == [[1, 2, 3], [4]]


def test_orphans_and_empty_input():
    assert build_batches([]) == []
    batches = build_batches([clause(1, 3), clause(2, 2), clause(3)])
    assert [[c.id for c in b.clauses] for b in batches] == [[1, 2], [3]]


def test_split_accounts_for_rendering_overhead_preserves_order_and_section():
    clauses = [clause(i, 1 if i == 1 else 2, "x" * 80) for i in range(1, 8)]
    batches = build_batches(clauses, max_chars=300)
    assert len(batches) > 1
    assert [c.id for b in batches for c in b.clauses] == list(range(1, 8))
    assert all(len(render(b)) <= 300 for b in batches)
    assert {b.section for b in batches} == {"Heading"}


def test_oversized_clause_is_whole_and_alone():
    batches = build_batches([clause(1, text="x" * 500), clause(2, 2)], max_chars=100)
    assert [len(b.clauses) for b in batches] == [1, 1]
    assert batches[0].clauses[0].text == "x" * 500


def test_render_has_ids_labels_body_and_default_size():
    assert MAX_BATCH_CHARS == 12000
    text = render(build_batches([clause(42)])[0])
    assert "[clause_id=42] 42 — Heading" in text
    assert "Body" in text


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_size(size):
    with pytest.raises(ValueError):
        build_batches([], max_chars=size)
