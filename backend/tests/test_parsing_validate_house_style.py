"""house style 期望必须是**部署方配置**，不是写死的。

原来写死 `("Introduction", "Roles and Responsibilities")`——那是样本那 6 份文档的
文风。对**每一份**外部机构的文档都会报「未找到应有的章节——解析可能不完整」，
而实际上解析得好好的。实测 HKMA TM-C-1 就是这样被误报的，那会是第一个真实用户
导入文档时看到的第一条假警报。
"""

from app.parsing.contract import ClauseNode, DocumentMeta, ParsedDocument
from app.parsing.validate import check_completeness

_EMPTY_META = DocumentMeta(
    title=None, version=None, owner=None, approver=None,
    approved_date=None, effective_date=None, doc_type=None,
)


def _parsed(*headings: str) -> ParsedDocument:
    return ParsedDocument(
        meta=_EMPTY_META,
        clauses=[ClauseNode(heading=h, text="body", level=1) for h in headings],
        warnings=[],
    )


def test_nothing_is_expected_by_default():
    """开箱即用不做任何 house style 假设——不认识的文风不是解析错误。"""
    assert check_completeness(_parsed("Purpose", "Scope")) == []


def test_a_deployment_can_say_what_its_documents_always_contain(monkeypatch):
    monkeypatch.setattr(
        "app.parsing.validate.EXPECTED_SECTIONS", ("Introduction", "Roles and Responsibilities")
    )

    warnings = check_completeness(_parsed("Introduction", "Scope"))

    assert len(warnings) == 1
    assert "Roles and Responsibilities" in warnings[0]


def test_nothing_is_reported_when_the_expected_sections_are_all_there(monkeypatch):
    monkeypatch.setattr("app.parsing.validate.EXPECTED_SECTIONS", ("Introduction",))

    assert check_completeness(_parsed("Introduction", "Scope")) == []
