from app.parsing.numbering import (
    NumberedHeading,
    assemble_tree,
    extract_headings,
    is_toc_line,
    is_version_history_line,
)

REAL_SHAPED_LINES = [
    "Change Log",
    "1.0        01/06/2021 Start version of the Procedure",
    "2.0        20/09/2022 Re-written according to Enterprise approach",
    "2.01       01/12/2022 Spelling errors fixed",
    "Table of Contents",
    "1 Role and Responsibility ..................................... 3",
    "4 Change Management Process .................................. 5",
    "4.1 Normal Change ............................................ 5",
    "1 Role and Responsibility",
    "The IT Division owns this procedure.",
    "4 Change Management Process",
    "4.1 Normal Change",
    "Normal changes follow the CAB cycle.",
    "4.1.1 Change Request",
    "A change request must be raised in the tool.",
]


def test_detects_toc_lines_by_dot_leaders():
    assert is_toc_line("4.1 Normal Change ............................ 5")
    assert not is_toc_line("4.1 Normal Change")
    assert not is_toc_line("The version is 1.0. See section 4.")


def test_detects_version_history_rows():
    assert is_version_history_line("2.01       01/12/2022 Spelling errors fixed")
    assert not is_version_history_line("4.1 Normal Change")


def test_extract_drops_toc_and_version_rows():
    headings, warnings = extract_headings(REAL_SHAPED_LINES)
    numbers = [heading.number for heading in headings]

    assert numbers == ["1", "4", "4.1", "4.1.1"]
    assert "1.0" not in numbers
    assert "2.01" not in numbers
    assert len(warnings) >= 1


def test_orphan_number_is_rejected():
    headings, _ = extract_headings(["1.0 Start version of the Procedure"])
    assert headings == []


def test_child_requires_its_parent():
    headings, _ = extract_headings(["4.1.1 Change Request"])
    assert headings == []


def test_duplicate_number_keeps_the_later_occurrence():
    headings, _ = extract_headings(["1 Scope", "some body text", "1 Scope"])
    assert len(headings) == 1
    assert headings[0].line_index == 2


def test_level_comes_from_dot_count():
    assert NumberedHeading(number="4", title="x", line_index=0).level == 1
    assert NumberedHeading(number="4.1", title="x", line_index=0).level == 2
    assert NumberedHeading(number="4.1.1", title="x", line_index=0).level == 3


def test_assemble_tree_nests_by_number():
    headings, _ = extract_headings(REAL_SHAPED_LINES)
    tree = assemble_tree(headings, REAL_SHAPED_LINES)

    assert [node.number for node in tree] == ["1", "4"]
    assert [node.number for node in tree[1].children] == ["4.1"]
    assert [node.number for node in tree[1].children[0].children] == ["4.1.1"]


def test_assemble_tree_captures_body_text():
    headings, _ = extract_headings(REAL_SHAPED_LINES)
    tree = assemble_tree(headings, REAL_SHAPED_LINES)

    assert tree[0].text == "The IT Division owns this procedure."
    assert tree[1].children[0].children[0].text == "A change request must be raised in the tool."


def test_assemble_tree_records_page_numbers():
    lines = ["1 Scope", "body", "2 Purpose"]
    tree = assemble_tree(headings=extract_headings(lines)[0], lines=lines, page_of={0: 3, 2: 4})
    assert tree[0].page_ref == 3
    assert tree[1].page_ref == 4


def test_empty_input_yields_nothing():
    assert extract_headings([]) == ([], [])
    assert assemble_tree([], []) == []


def test_the_real_trap_ratio_is_reproduced():
    headings, _ = extract_headings(REAL_SHAPED_LINES)
    numbered_lines = [
        line for line in REAL_SHAPED_LINES if line[:1].isdigit() and " " in line
    ]
    # 3 个版本历史行 + 3 个目录行 + 4 个正文条款行。
    assert len(numbered_lines) == 10
    assert len(headings) == 4
