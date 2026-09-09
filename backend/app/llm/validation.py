"""结构化输出校验——spec §6.3 的第 2 道闸。

第 3、4 道闸（clause_id 存在性、原文回验）依赖 Clause 表，属 M4。
这里预留 CitationValidator 插槽，M4 填入真实实现即可，runner 不必改动。
"""

import json
import re
import unicodedata
from typing import Any, Protocol

from jsonschema import Draft202012Validator

_FENCED = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


class ValidationFailure(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# PDF extraction leaves typographic artifacts the model silently canonicalises when
# it copies a quote. Folding them keeps gate 4 literal — a fabricated or altered
# word still fails the substring test — while it stops rejecting faithful quotes.
_FOLD = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2015": "-", "\u2212": "-",
    "\u2022": " ", "\u2023": " ", "\u25aa": " ", "\u25cf": " ", "\u00b7": " ",
})
_LINE_WRAP = re.compile(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).translate(_FOLD)
    return " ".join(_LINE_WRAP.sub("-", folded).split())


def extract_json(raw: str) -> dict[str, Any]:
    """容忍模型把 JSON 包在代码块里或前后带解释文字。"""
    candidates: list[str] = []

    fenced = _FENCED.search(raw)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(raw.strip())

    # 兜底：取第一个 { 到最后一个 } 之间的内容
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValidationFailure("模型输出中没有找到合法的 JSON 对象")


def validate(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda e: e.path)
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "(根)"
        raise ValidationFailure(f"{location}: {first.message}")
    return payload


def correction_prompt(previous: str, reason: str) -> str:
    return (
        "你上一次的输出不符合要求的 JSON Schema。\n"
        f"上一次的输出：\n{previous}\n\n"
        f"问题：{reason}\n\n"
        "请只输出修正后的 JSON 对象，不要任何解释文字、不要代码块标记。"
    )


class CitationValidator(Protocol):
    """引用校验插槽。返回 None 表示通过，返回字符串表示失败原因。"""

    async def check(self, payload: dict[str, Any]) -> str | None: ...


class NullCitationValidator:
    """M1 的默认实现。M4 会用查库 + 原文回验的实现替换它。"""

    async def check(self, payload: dict[str, Any]) -> str | None:
        return None
