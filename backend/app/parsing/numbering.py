"""十进制编号到条款层级，并过滤已知版面陷阱。"""

import re
from dataclasses import dataclass

from app.parsing.contract import ClauseNode

# 第 2 组捕获编号后是否带点：带点的是正文列表项，不是标题
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)(\.?)\s+(\S.*?)\s*$")
# 目录形态之一：引导点
_DOT_LEADER = re.compile(r"\.{4,}")
# 目录形态之二：行尾跟着页码。实测这批文件的目录不带引导点，而是
# "1 Introduction 1" 这种形状——只认引导点会让 84 条目录行全部漏进来。
_TOC_TRAILING_PAGE = re.compile(r"^\d+(?:\.\d+)*\s+.+?\s+\d{1,3}$")
_VERSION_ROW = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\d{2}/\d{2}/\d{4}\b")
# 页脚。pdfplumber 会把字距拉开的页码渲染成 "1 | P a g e"
_PAGE_FOOTER = re.compile(
    r"^\s*\d+\s*\|\s*P\s*a\s*g\s*e\b|^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE
)


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
    """两种目录形态：带引导点的，和行尾跟页码的。"""
    return bool(_DOT_LEADER.search(line)) or bool(_TOC_TRAILING_PAGE.match(line.strip()))


def is_page_footer(line: str) -> bool:
    return bool(_PAGE_FOOTER.match(line))


def is_list_item(number: str, trailing_dot: str) -> bool:
    """"1. Click Add Account" 是操作步骤，不是条款。

    实测这批文件里 41 条带点编号**全部**是单段的正文列表项，真标题一律不带点。
    只排单段带点的，多段带点（4.1.）仍按标题处理，留出余地。
    """
    return trailing_dot == "." and "." not in number


def is_version_history_line(line: str) -> bool:
    return bool(_VERSION_ROW.match(line))


def extract_headings(lines: list[str]) -> tuple[list[NumberedHeading], list[str]]:
    warnings: list[str] = []
    seen: dict[str, NumberedHeading] = {}
    dropped = {"toc": 0, "version": 0, "orphan": 0, "footer": 0, "list": 0, "duplicate": 0}

    for index, line in enumerate(lines):
        match = _NUMBERED.match(line)
        if match is None:
            continue
        if is_page_footer(line):
            dropped["footer"] += 1
            continue
        if is_toc_line(line):
            dropped["toc"] += 1
            continue
        if is_version_history_line(line):
            dropped["version"] += 1
            continue
        if is_list_item(match.group(1), match.group(2)):
            dropped["list"] += 1
            continue

        heading = NumberedHeading(
            number=match.group(1), title=match.group(3), line_index=index
        )
        parent = heading.parent_number
        if parent is not None and parent not in seen:
            dropped["orphan"] += 1
            continue
        # 保留**第一次**出现。目录、页脚、列表项都已挡掉，剩下的重复只可能是
        # 正文噪声；而正文噪声总在真条款之后——保留后一次会让文末的噪声顶掉
        # 开头的真条款，并连带把它的子条款打成孤儿，整棵树就塌了。
        if heading.number in seen:
            dropped["duplicate"] += 1
            continue
        seen[heading.number] = heading

    labels = {
        "toc": "目录行",
        "version": "版本历史行",
        "orphan": "孤儿编号",
        "footer": "页脚行",
        "list": "正文列表项",
        "duplicate": "重复编号",
    }
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
