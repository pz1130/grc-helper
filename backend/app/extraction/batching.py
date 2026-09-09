"""Deterministic section batches; clauses are never split or discarded."""

from dataclasses import dataclass

from app.clauses.models import Clause
from app.common.batching import group_by_top_level

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
    groups: list[list[Clause]] = []
    sections: dict[int, str] = {}
    for clause in clauses:
        if clause.level <= 1 or not groups:
            groups.append([])
            sections[len(groups) - 1] = clause.heading or ""
        groups[-1].append(clause)
    batches: list[Batch] = []
    for position, group in enumerate(groups):
        section = sections[position]
        header_size = len(render(Batch([], section)))
        for chunk in group_by_top_level(
            group,
            level_of=lambda _: 2,
            render_size=lambda clause, section=section, header_size=header_size: (
                len(render(Batch([clause], section))) - header_size
            ),
            max_chars=max_chars,
            header_size=header_size,
        ):
            batches.append(Batch(chunk, section))
    return batches
