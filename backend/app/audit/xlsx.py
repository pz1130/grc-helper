"""Bounded, deterministic import of audit questions from the first XLSX sheet."""

from app.matrix.template import Sheet, read_sheet

QUESTION_HEADERS = frozenset({"question", "question text", "audit question", "问题", "审计问题"})
LANGUAGE_HEADERS = frozenset({"language", "language code", "语言", "语言代码"})
LANGUAGES = {
    "en": "en",
    "english": "en",
    "英文": "en",
    "英语": "en",
    "zh": "zh",
    "chinese": "zh",
    "中文": "zh",
    "汉语": "zh",
}


def _header(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())


def _column(headers: list[str], aliases: frozenset[str]) -> int | None:
    matches = [index for index, value in enumerate(headers) if _header(value) in aliases]
    if len(matches) > 1:
        raise ValueError("Excel 包含重复的问题或语言列")
    return matches[0] if matches else None


def parse_questions(content: bytes) -> list[tuple[str, str]]:
    sheet: Sheet = read_sheet(content, max_rows=201)
    question_column = _column(sheet.headers, QUESTION_HEADERS)
    language_column = _column(sheet.headers, LANGUAGE_HEADERS)
    if question_column is None:
        raise ValueError("Excel 缺少“审计问题”或“question”列")
    rows: list[tuple[str, str]] = []
    errors: list[str] = []
    for row_number, row in enumerate(sheet.rows, start=2):
        question = row[question_column].strip() if question_column < len(row) else ""
        if not question:
            errors.append(f"第 {row_number} 行审计问题为空")
            continue
        if len(question) > 10_000:
            errors.append(f"第 {row_number} 行审计问题超过 10000 字符")
            continue
        raw_language = (
            row[language_column].strip().casefold()
            if language_column is not None and language_column < len(row)
            else "en"
        )
        language = LANGUAGES.get(raw_language or "en")
        if language is None:
            errors.append(f"第 {row_number} 行语言无效：{raw_language}")
            continue
        rows.append((question, language))
    if len(sheet.rows) > 200:
        errors.append("一次最多导入 200 个问题")
    if errors:
        raise ValueError("；".join(errors[:20]))
    if not rows:
        raise ValueError("Excel 没有可导入的审计问题")
    return rows
