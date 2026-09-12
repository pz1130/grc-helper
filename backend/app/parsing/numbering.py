"""十进制编号到条款层级，并过滤已知版面陷阱。"""

import re
from dataclasses import dataclass

from app.parsing.contract import ClauseNode
from app.parsing.headings import acts_as_headings

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

    **这条规则什么时候生效，由每份文档自己决定**（见 headings.acts_as_headings）。
    它原本是全局常量，依据是"实测这批文件里 41 条带点编号全部是列表项"——
    那是 6 份样本的写法。HKMA / KBC / AlRayan 的章节标题恰好一律带点，
    全局生效会把它们的顶层标题整批丢掉，子标题跟着变孤儿。
    """
    return trailing_dot == "." and "." not in number


def is_version_history_line(line: str) -> bool:
    return bool(_VERSION_ROW.match(line))


def _noise(line: str) -> str | None:
    """目录、页脚、版本历史——三类与文风无关的噪声，先挡掉再谈结构。"""
    if is_page_footer(line):
        return "footer"
    if is_toc_line(line):
        return "toc"
    if is_version_history_line(line):
        return "version"
    return None


def _ancestors(number: str) -> list[str]:
    """"4.1.1" → ["4", "4.1"]，由外向内。"""
    parts = number.split(".")
    return [".".join(parts[:cut]) for cut in range(1, len(parts))]


def extract_headings(lines: list[str]) -> tuple[list[NumberedHeading], list[str]]:
    warnings: list[str] = []
    seen: dict[str, NumberedHeading] = {}
    dropped = {"toc": 0, "version": 0, "orphan": 0, "footer": 0, "list": 0, "duplicate": 0}

    # 第一遍只做一件事：这份文档里的 `N.` 是章节标题还是正文列表项。
    # 判据是"它们有没有子号挂上去"，只看这一份文档自己（见 headings.py）。
    survey = [
        match.group(1)
        for line in lines
        if _noise(line) is None and (match := _NUMBERED.match(line))
    ]
    dotted_are_headings = acts_as_headings(survey)

    ordered: list[NumberedHeading] = []
    synthetic: set[str] = set()

    def remember(heading: NumberedHeading) -> None:
        seen[heading.number] = heading
        ordered.append(heading)

    for index, line in enumerate(lines):
        match = _NUMBERED.match(line)
        if match is None:
            continue
        if (kind := _noise(line)) is not None:
            dropped[kind] += 1
            continue
        if not dotted_are_headings and is_list_item(match.group(1), match.group(2)):
            dropped["list"] += 1
            continue

        heading = NumberedHeading(
            number=match.group(1), title=match.group(3), line_index=index
        )
        # 保留**第一次**出现。目录、页脚、列表项都已挡掉，剩下的重复只可能是
        # 正文噪声；而正文噪声总在真条款之后——保留后一次会让文末的噪声顶掉
        # 开头的真条款，并连带把它的子条款打成孤儿，整棵树就塌了。
        if heading.number in seen:
            if heading.number in synthetic:
                # 先前为了接住孤儿补出来的占位，真标题出现了就把名字换上。
                # 位置仍用占位那一处，免得父节点排到子节点后面去。
                position = ordered.index(seen[heading.number])
                real = NumberedHeading(
                    number=heading.number,
                    title=heading.title,
                    line_index=seen[heading.number].line_index,
                )
                ordered[position] = real
                seen[heading.number] = real
                synthetic.discard(heading.number)
            else:
                dropped["duplicate"] += 1
            continue

        # 孤儿不再丢弃，补出缺的父节点。实测丢弃的代价：05_TD 丢掉 165 条、
        # 条款数归零，16_KBC 丢掉 244 条只剩 4 条——丢的不是噪声，是整棵树。
        # 占位用编号本身当标题：没有正文可依据，而空标题下游更难处理。
        for ancestor in _ancestors(heading.number):
            if ancestor not in seen:
                remember(NumberedHeading(number=ancestor, title=ancestor, line_index=index))
                synthetic.add(ancestor)
                dropped["orphan"] += 1
        remember(heading)

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

    # 稳定排序：补出来的父节点与孩子共用行号，插入顺序保证父在前。
    return sorted(ordered, key=lambda heading: heading.line_index), warnings


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
