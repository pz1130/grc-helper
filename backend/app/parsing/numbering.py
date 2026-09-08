"""十进制编号到条款层级，并过滤已知版面陷阱。"""

import re
from dataclasses import dataclass

from app.parsing.contract import ClauseNode

_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*?)\s*$")
_DOT_LEADER = re.compile(r"\.{4,}")
_VERSION_ROW = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\d{2}/\d{2}/\d{4}\b")


@dataclass(frozen=True)
class NumberedHeading:
    number: str
    title: str
    line_index: int

    @property
    def level(self) -> int:
        return self.number.count(".") + 1

    @property
    def parent_number(self) -> str | None:
        return self.number.rsplit(".", 1)[0] if "." in self.number else None


def is_toc_line(line: str) -> bool:
    return bool(_DOT_LEADER.search(line))


def is_version_history_line(line: str) -> bool:
    return bool(_VERSION_ROW.match(line))


def extract_headings(lines: list[str]) -> tuple[list[NumberedHeading], list[str]]:
    warnings: list[str] = []
    seen: dict[str, NumberedHeading] = {}
    dropped = {"toc": 0, "version": 0, "orphan": 0}

    for index, line in enumerate(lines):
        match = _NUMBERED.match(line)
        if match is None:
            continue
        if is_toc_line(line):
            dropped["toc"] += 1
            continue
        if is_version_history_line(line):
            dropped["version"] += 1
            continue

        heading = NumberedHeading(
            number=match.group(1).rstrip("."), title=match.group(2), line_index=index
        )
        parent = heading.parent_number
        if parent is not None and parent not in seen:
            dropped["orphan"] += 1
            continue
        seen[heading.number] = heading

    labels = {"toc": "目录行", "version": "版本历史行", "orphan": "孤儿编号"}
    for kind, count in dropped.items():
        if count:
            warnings.append(f"已跳过 {count} 条{labels[kind]}")

    return sorted(seen.values(), key=lambda heading: heading.line_index), warnings


def assemble_tree(
    headings: list[NumberedHeading],
    lines: list[str],
    page_of: dict[int, int] | None = None,
) -> list[ClauseNode]:
    if not headings:
        return []

    pages = page_of or {}
    nodes: dict[str, ClauseNode] = {}
    roots: list[ClauseNode] = []

    for position, heading in enumerate(headings):
        end = headings[position + 1].line_index if position + 1 < len(headings) else len(lines)
        body = "\n".join(
            line.strip() for line in lines[heading.line_index + 1 : end] if line.strip()
        )
        node = ClauseNode(
            heading=heading.title,
            text=body,
            level=heading.level,
            number=heading.number,
            page_ref=pages.get(heading.line_index),
        )
        nodes[heading.number] = node

        parent = nodes.get(heading.parent_number) if heading.parent_number else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)

    return roots
