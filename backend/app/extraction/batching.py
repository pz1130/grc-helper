"""Deterministic section batches; clauses are never split or discarded."""

from dataclasses import dataclass

from app.clauses.models import Clause

MAX_BATCH_CHARS = 12000


@dataclass(frozen=True)
class Batch:
    clauses: list[Clause]
    section: str


def render(batch: Batch) -> str:
    lines = [f"# Section: {batch.section}", ""]
    for clause in batch.clauses:
        lines.append(f"[clause_id={clause.id}] {clause.citation_label} — {clause.heading}")
        if clause.text:
            lines.append(clause.text)
        lines.append("")
    return "\n".join(lines)


def build_batches(clauses: list[Clause], *, max_chars: int = MAX_BATCH_CHARS) -> list[Batch]:
    """Preserve input order. A single oversized clause stays intact in its own batch."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    groups: list[Batch] = []
    for clause in clauses:
        if clause.level <= 1 or not groups:
            groups.append(Batch([], clause.heading or ""))
        groups[-1].clauses.append(clause)
    batches: list[Batch] = []
    for group in groups:
        current: list[Clause] = []
        size = len(render(Batch([], group.section)))
        header_size = size
        for clause in group.clauses:
            length = len(render(Batch([clause], group.section))) - header_size
            if current and size + length > max_chars:
                batches.append(Batch(current, group.section))
                current, size = [], header_size
            current.append(clause)
            size += length
        if current:
            batches.append(Batch(current, group.section))
    return batches
