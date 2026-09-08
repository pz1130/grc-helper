"""house style completeness checks."""

from app.parsing.contract import ClauseNode, ParsedDocument

EXPECTED_SECTIONS: tuple[str, ...] = ("Introduction", "Roles and Responsibilities")


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
