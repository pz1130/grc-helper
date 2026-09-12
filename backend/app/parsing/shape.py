"""条款树的**形状**检查——与文风无关，只问"切开了没有"。

这套判据原先只活在 `tests/test_corpus_report.py` 里，开发者跑 `make corpus` 才看得到。
产品自己不检查：用户上传一份切成一坨的文档，`status` 照样是 active，界面上什么都不说，
直到他点开某个控制点、发现出处指向"条款 1"才知道不对。

判据只看形状，不看文风——一份文件被压成一坨，不论出自哪家机构都是错的；
反过来 6 页切出 97 条也是错的。

阈值取自 36 份实测（15 份外部 PDF + 14 份外部 docx + 6 份样本 + 1 份新 docx）：

    最大块占比   正常 7–33%，样本里最高 56%（一份 2.4k 字的短文件）
                 塌掉的是 70% / 84% / 100% / 100%
    条/千字      PDF 正常 0.29–0.43，docx 正常 1.31–3.73
                 塌掉的 0.03 / 0.04 / 0.10，过切的 13.34
    标题最长     正常 28–144 字；把正文当标题的 288 / 325 / 479 / 860 / 992 / 1051
    编号唯一率   正常 100%；段落编号被当成章节编号的 34% / 46% / 81% / 83% / 84% / 92%

**只警告，不拦截。** 用户可能明知文档难啃也要先导进来看看——那是他的判断，
不是解析器的。警告会写进 `Document.parse_warnings`，文档列表与详情页都显示。
"""

from app.parsing.contract import ClauseNode, ParsedDocument

MIN_CHARS_TO_JUDGE = 3000
MAX_SINGLE_CLAUSE_SHARE = 0.60
MIN_CLAUSES_PER_1K = 0.15
MAX_CLAUSES_PER_1K = 8.0
MAX_HEADING_CHARS = 250
MIN_DISTINCT_NUMBER_RATIO = 0.95


def walk(nodes: list[ClauseNode]):
    for node in nodes:
        yield node
        yield from walk(node.children)


def assess_shape(parsed: ParsedDocument) -> list[str]:
    """返回给人看的警告；形状正常时是空列表。"""
    nodes = list(walk(parsed.clauses))
    total = sum(len(node.text or "") for node in nodes)
    if total < MIN_CHARS_TO_JUDGE:
        # 两页的通函条款本来就少，形状判据不适用。
        return []

    warnings: list[str] = []
    sections = [node for node in nodes if node.kind == "section"]

    if not sections:
        warnings.append(
            f"这份文档产出 {len(nodes)} 条，全部是表格，没有任何章节条款"
            "——条款树没建起来，引用会指不到确定的位置"
        )

    biggest = max((len(node.text or "") for node in nodes), default=0)
    share = biggest / total
    if share > MAX_SINGLE_CLAUSE_SHARE:
        warnings.append(
            f"最大的一条条款装下了 {share:.0%} 的正文——条款树没切开，建议人工核对"
        )

    per_k = len(nodes) / (total / 1000)
    if per_k < MIN_CLAUSES_PER_1K:
        warnings.append(f"每千字只有 {per_k:.2f} 条条款（共 {len(nodes)} 条）——疑似塌树")
    elif per_k > MAX_CLAUSES_PER_1K:
        warnings.append(
            f"每千字有 {per_k:.2f} 条条款（共 {len(nodes)} 条）——疑似把正文行当成了条款"
        )

    if sections:
        longest = max(sections, key=lambda node: len(node.heading))
        if len(longest.heading) > MAX_HEADING_CHARS:
            warnings.append(
                f"最长的标题有 {len(longest.heading)} 字——那是一段正文，不是标题"
            )

        numbers = [node.number for node in sections if (node.number or "").strip()]
        if numbers:
            ratio = len(set(numbers)) / len(numbers)
            if ratio < MIN_DISTINCT_NUMBER_RATIO:
                warnings.append(
                    f"{len(numbers)} 条带编号的条款只有 {len(set(numbers))} 个不同编号"
                    "——编号不唯一，审计引用指不到确定的一条"
                )

    return warnings
