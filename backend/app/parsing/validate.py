"""house style completeness checks。

**默认什么都不期望。** 原来写死 `("Introduction", "Roles and Responsibilities")`，
那是样本那 6 份文档的文风；对每一份外部机构的文档都会报「未找到应有的章节——
解析可能不完整」，而它们解析得好好的。实测 HKMA TM-C-1 就是这样被误报的。

知道自己文风的部署方用 `PARSING_EXPECTED_SECTIONS` 配置（逗号分隔），
那时这条检查才有意义——它抓的是"解析漏掉了文档开头"这类真问题。
"""

import os

from app.parsing.contract import ClauseNode, ParsedDocument

EXPECTED_SECTIONS: tuple[str, ...] = tuple(
    piece.strip()
    for piece in os.environ.get("PARSING_EXPECTED_SECTIONS", "").split(",")
    if piece.strip()
)


def _all_headings(nodes: list[ClauseNode]) -> list[str]:
    headings: list[str] = []
    for node in nodes:
        headings.append(node.heading.strip().casefold())
        headings.extend(_all_headings(node.children))
    return headings


def check_completeness(parsed: ParsedDocument) -> list[str]:
    present = set(_all_headings(parsed.clauses))
    missing = [section for section in EXPECTED_SECTIONS if section.casefold() not in present]
    if not missing:
        return []
    return [f"未找到应有的章节：{'、'.join(missing)}——解析可能不完整，建议人工核对"]
