"""编号词汇表：认编号，不判断是不是标题。

同一个 `1.` 在一份文档里是章节标题、在另一份里是操作步骤——那是仲裁的事
（test_parsing_headings.py），词汇表只管"这行开头有没有编号、编号是什么"。
"""

import pytest

from app.parsing.vocab import VOCABULARIES, parse_label


def test_decimal_numbers_parse_with_or_without_a_trailing_dot():
    # 样本语料不带点，HKMA / Arab Bank 带点。两种都要认出来，是不是标题另说。
    assert parse_label("3.4.2 Escalation").parts == (3, 4, 2)
    assert parse_label("1.1. Background").parts == (1, 1)
    assert parse_label("1.1. Background").trailing_dot is True
    assert parse_label("3.4.2 Escalation").trailing_dot is False


def test_the_title_comes_back_without_the_label():
    found = parse_label("1.1. Background")
    assert found.title == "Background"
    assert found.label == "1.1."


def test_parenthesised_labels_parse():
    """06_OCC_CFR 有 226 行这种形态，现有正则一行都认不出。"""
    assert parse_label("(a) The rules set forth in this part").kind == "paren"
    assert parse_label("(a) The rules set forth in this part").parts == (1,)
    assert parse_label("(2) Pursuant to section 907(b)").parts == (2,)


def test_letter_labels_parse():
    """03_Scotiabank 的 A.–D.，制表符分隔。"""
    found = parse_label("C.\tReporting")
    assert found.kind == "letter"
    assert found.parts == (3,)
    assert found.title == "Reporting"


def test_a_sentence_is_not_a_label():
    assert parse_label("The CAB is convened twice a week") is None
    assert parse_label("") is None
    assert parse_label("   ") is None


def test_a_year_is_not_a_section_number():
    """没有哪份文档有第 2024 节。四位以上的单段编号一律不认——
    这是形状判断，不是文风判断。"""
    assert parse_label("2024 was a difficult year for the sector") is None
    assert parse_label("2024. Review of the year") is None
    # 但多段的不受影响：4.2024 不是年份，是编号
    assert parse_label("4.2024 Something").parts == (4, 2024)


def test_a_label_with_no_title_is_not_a_label():
    assert parse_label("1.") is None
    assert parse_label("(a)") is None


@pytest.mark.parametrize("line", ["1. Introduction", "(b) Procedures", "D. Composition"])
def test_every_vocabulary_reports_its_kind(line):
    assert parse_label(line).kind in {vocabulary.kind for vocabulary in VOCABULARIES}


def test_the_vocabulary_list_leaves_room_for_more():
    """中文词汇表（OQ-17）本期不做，但要能加进来而不改调用方。"""
    assert len(VOCABULARIES) >= 3
    for vocabulary in VOCABULARIES:
        assert callable(vocabulary.match)
        assert isinstance(vocabulary.kind, str)
