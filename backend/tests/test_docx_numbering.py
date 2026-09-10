"""Word 自动编号的还原。

Word 的标题编号不在文字里：`w:t` 只有 "Introduction"，前面那个 "1" 是渲染时按
numbering.xml 画上去的。不还原就只能让 citation_label 退化成标题路径，而审计
引用要的是 3.4.2。
"""

import re

import pytest
from docx import Document

from app.parsing.docx_numbering import HeadingNumbering, format_counter


def test_decimal_letters_and_roman():
    assert format_counter(3, "decimal") == "3"
    assert format_counter(1, "lowerLetter") == "a"
    assert format_counter(27, "lowerLetter") == "aa"
    assert format_counter(4, "upperLetter") == "D"
    assert format_counter(9, "lowerRoman") == "ix"
    assert format_counter(2024, "upperRoman") == "MMXXIV"


def test_an_unknown_format_returns_none_instead_of_guessing():
    """错的条款号比没有更糟——审计引用会指向不存在的位置。"""
    assert format_counter(1, "bullet") is None
    assert format_counter(1, "chineseCounting") is None


# ---- 状态机 ----


class _Stub:
    """最小的段落替身：只需要 _p（找 pPr）与 style.style_id。"""

    def __init__(self, root, style_id: str) -> None:
        self._p = root
        self.style = type("S", (), {"style_id": style_id})()


def _docx_with_numbering(tmp_path, levels: str, styles: str):
    """造一个带指定 numbering/styles 的 docx，用 python-docx 打开。"""
    import shutil
    import zipfile

    source = tmp_path / "base.docx"
    Document().save(source)
    target = tmp_path / "built.docx"
    shutil.copy(source, target)

    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    numbering = f'<w:numbering {W}>{levels}</w:numbering>'
    style_xml = f'<w:styles {W}>{styles}</w:styles>'
    with zipfile.ZipFile(source) as src:
        names = [n for n in src.namelist() if n not in
                 ("word/numbering.xml", "word/styles.xml")]
        parts = {n: src.read(n) for n in names}
        rels = src.read("word/_rels/document.xml.rels").decode()
    if "numbering.xml" not in rels:
        rels = rels.replace("</Relationships>",
            '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            "</Relationships>")
    parts["word/_rels/document.xml.rels"] = rels.encode()
    with zipfile.ZipFile(target, "w") as out:
        for name, data in parts.items():
            out.writestr(name, data)
        out.writestr("word/numbering.xml", numbering)
        out.writestr("word/styles.xml", style_xml)
    return Document(str(target))


LEVELS = "".join(
    f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
    f'<w:lvlText w:val="{".".join("%" + str(k + 1) for k in range(i + 1))}"/></w:lvl>'
    for i in range(4)
)
NUMBERING = (
    f'<w:abstractNum w:abstractNumId="15">{LEVELS}</w:abstractNum>'
    '<w:num w:numId="3"><w:abstractNumId w:val="15"/></w:num>'
)
# Heading1 只声明 ilvl，numId 要沿 basedOn 链从 Heading2 继承——真实文档就是这样。
STYLES = (
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:basedOn w:val="Heading2"/>'
    '<w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2">'
    '<w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="3"/></w:numPr></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading3"><w:basedOn w:val="Heading2"/>'
    '<w:pPr><w:numPr><w:ilvl w:val="2"/></w:numPr></w:pPr></w:style>'
)


def _sequence(document, plan: list[str]) -> list[str | None]:
    from docx.oxml.ns import qn

    numbering = HeadingNumbering(document)
    out = []
    for style_id in plan:
        paragraph = document.add_paragraph()
        paragraph._p.get_or_add_pPr()
        out.append(numbering.number_for(_Stub(paragraph._p, style_id)))
        assert paragraph._p.find(qn("w:pPr")) is not None
    return out


def test_numbers_nest_and_reset(tmp_path):
    document = _docx_with_numbering(tmp_path, NUMBERING, STYLES)
    got = _sequence(document, [
        "Heading1", "Heading2", "Heading2", "Heading1", "Heading2", "Heading3", "Heading3",
        "Heading2", "Heading1",
    ])
    assert got == ["1", "1.1", "1.2", "2", "2.1", "2.1.1", "2.1.2", "2.2", "3"]


def test_num_id_is_inherited_through_the_based_on_chain(tmp_path):
    """Heading1 自己没有 numId，只有 ilvl——真实文档就是这样写的。"""
    document = _docx_with_numbering(tmp_path, NUMBERING, STYLES)
    assert _sequence(document, ["Heading1"]) == ["1"]


def test_a_paragraph_with_no_numbering_gets_nothing(tmp_path):
    document = _docx_with_numbering(tmp_path, NUMBERING, STYLES)
    assert _sequence(document, ["BodyText"]) == [None]


def test_a_document_without_numbering_part_does_not_explode(tmp_path):
    """没有 numbering.xml 的 docx 要安静地返回 None，而不是抛异常。"""
    document = Document()
    numbering = HeadingNumbering(document)
    paragraph = document.add_paragraph()
    paragraph._p.get_or_add_pPr()
    assert numbering.number_for(_Stub(paragraph._p, "Heading1")) is None


# ---- 真实文档 ----

REAL = "/samples/Acme-incident-management.docx"
EXPECTED_HEAD = ["1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "2", "2.1", "2.2", "2.3"]


@pytest.mark.skipif(not __import__("pathlib").Path(REAL).exists(),
                    reason="需挂载 sample docs，见 make corpus")
def test_the_real_document_numbers_match_its_own_table_of_contents():
    """未改动的章节与文档自带目录逐条一致。

    目录本身是**过期的**：文档后来插入了一个一级标题并把原来的降了一级，目录没
    重新生成。所以只比对目录仍然覆盖的部分——这也正是当初放弃「直接读目录」
    方案的理由，那样会在这份文档上算出错的编号。
    """
    document = Document(REAL)
    numbering = HeadingNumbering(document)
    heading = re.compile(r"^Heading (\d+)$")
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    got = []
    for paragraph in document.paragraphs:
        if not heading.match(paragraph.style.name or ""):
            continue
        number = numbering.number_for(paragraph)
        text = "".join(t.text or "" for t in paragraph._p.iter(f"{W}t")).strip()
        if text:
            got.append(number)

    assert got[:len(EXPECTED_HEAD)] == EXPECTED_HEAD
    assert got[-2:] == ["4", "5"], "尾部两节未改动，编号应当仍是 4 与 5"
    assert all(n is not None for n in got), "32 条标题此前一个编号都没有"
