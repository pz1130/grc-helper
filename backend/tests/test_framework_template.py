from app.frameworks.template import parse_rows

HEADERS = ["code", "title", "description", "parent_code", "attributes_json"]


def rows(*values):
    return [list(value) for value in values]


def test_a_valid_forest_parses_with_levels_derived_from_parents():
    parsed, report = parse_rows(HEADERS, rows(
        ["PR", "Protect", "", "", ""],
        ["PR.AA", "Identity", "", "PR", ""],
        ["PR.AA-01", "Identities managed", "Text.", "PR.AA", ""],
        ["DE", "Detect", "", "", ""],
    ))
    assert report == []
    assert [(r.code, r.level) for r in parsed] == [
        ("PR", 1), ("PR.AA", 2), ("PR.AA-01", 3), ("DE", 1)]


def test_multiple_roots_are_legal():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "", ""], ["B", "b", "", "", ""]))
    assert report == []


def test_duplicate_codes_are_reported():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "", ""], ["A", "b", "", "", ""]))
    assert any("重复" in line for line in report)


def test_parent_code_pointing_nowhere_is_reported():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "ZZZ", ""]))
    assert any("ZZZ" in line for line in report)


def test_a_parent_cycle_is_reported():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "B", ""], ["B", "b", "", "A", ""]))
    assert any("成环" in line for line in report)


def test_a_self_parent_is_reported():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "A", ""]))
    assert any("成环" in line for line in report)


def test_missing_required_column_is_reported():
    _, report = parse_rows(["code", "description"], rows(["A", ""]))
    assert any("title" in line for line in report)


def test_blank_required_cell_is_reported():
    _, report = parse_rows(HEADERS, rows(["", "a", "", "", ""]))
    assert any("必填" in line for line in report)


def test_attributes_json_is_parsed_and_bad_json_is_reported():
    parsed, report = parse_rows(HEADERS, rows(
        ["A", "a", "", "", '{"baselines": ["moderate"], "is_requirement": true}']))
    assert report == []
    assert parsed[0].attributes == {"baselines": ["moderate"], "is_requirement": True}

    _, bad = parse_rows(HEADERS, rows(["A", "a", "", "", "{not json"]))
    assert any("attributes_json" in line for line in bad)


def test_attributes_json_must_be_an_object():
    _, report = parse_rows(HEADERS, rows(["A", "a", "", "", "[1,2]"]))
    assert any("attributes_json" in line for line in report)


def test_depth_beyond_the_limit_is_reported():
    from app.frameworks.template import MAX_DEPTH

    chain = [["N0", "n0", "", "", ""]]
    for i in range(1, MAX_DEPTH + 1):
        chain.append([f"N{i}", f"n{i}", "", f"N{i - 1}", ""])
    _, report = parse_rows(HEADERS, chain)
    assert any("层级" in line for line in report)


def test_empty_sheet_is_reported():
    _, report = parse_rows(HEADERS, [])
    assert any("没有数据行" in line for line in report)
