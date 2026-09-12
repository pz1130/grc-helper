"""编号词汇表：认出一行开头的编号，**不判断它是不是标题**。

同一个 `1.` 在一份文档里是章节标题（HKMA 的 `1. Introduction`），在另一份里是
操作步骤（`1. Click Add Account`）。那个判断依赖整篇文档的自洽性，属于
`headings.py` 的仲裁；这里只回答"这行开头有没有编号、编号是什么"。

实测 36 份文档，英文就用到三种词汇：

    1.1. Background            decimal   样本语料、HKMA、Arab Bank
    (a) The rules set forth    paren     06_OCC_CFR，226 行
    C.  Reporting              letter    03_Scotiabank 的 A.–D.

中文（`第三章` / `一、` / `（一）`）是 OQ-17，本期不实现——但 `Vocabulary`
这个协议就是给它留的位置：加一个实现、往 `VOCABULARIES` 里加一行即可，
调用方一个字不用改。
"""

import re
from dataclasses import dataclass
from typing import Protocol

# 单段编号超过这个值就不是编号，是年份或金额。没有哪份文档有第 2024 节。
# 这是**形状**判断，不是文风判断——换哪家机构都成立。
MAX_SINGLE_PART = 999


@dataclass(frozen=True)
class Numbering:
    label: str
    parts: tuple[int, ...]
    kind: str
    title: str
    trailing_dot: bool


class Vocabulary(Protocol):
    kind: str

    def match(self, line: str) -> Numbering | None: ...


@dataclass(frozen=True)
class _Decimal:
    kind: str = "decimal"
    _re: re.Pattern = re.compile(r"^\s*(\d+(?:\.\d+)*)(\.?)[ \t]+(\S.*?)\s*$")

    def match(self, line: str) -> Numbering | None:
        found = self._re.match(line)
        if found is None:
            return None
        parts = tuple(int(piece) for piece in found.group(1).split("."))
        if len(parts) == 1 and parts[0] > MAX_SINGLE_PART:
            return None
        return Numbering(
            label=found.group(1) + found.group(2),
            parts=parts,
            kind=self.kind,
            title=found.group(3),
            trailing_dot=found.group(2) == ".",
        )


@dataclass(frozen=True)
class _Paren:
    kind: str = "paren"
    _re: re.Pattern = re.compile(r"^\s*\((\d{1,3}|[a-zA-Z])\)[ \t]+(\S.*?)\s*$")

    def match(self, line: str) -> Numbering | None:
        found = self._re.match(line)
        if found is None:
            return None
        token = found.group(1)
        part = int(token) if token.isdigit() else ord(token.lower()) - ord("a") + 1
        return Numbering(
            label=f"({token})",
            parts=(part,),
            kind=self.kind,
            title=found.group(2),
            trailing_dot=False,
        )


@dataclass(frozen=True)
class _Letter:
    kind: str = "letter"
    _re: re.Pattern = re.compile(r"^\s*([A-Z])\.[ \t]+(\S.*?)\s*$")

    def match(self, line: str) -> Numbering | None:
        found = self._re.match(line)
        if found is None:
            return None
        return Numbering(
            label=f"{found.group(1)}.",
            parts=(ord(found.group(1)) - ord("A") + 1,),
            kind=self.kind,
            title=found.group(2),
            trailing_dot=True,
        )


# 顺序即优先级。三种形态互不重叠，所以顺序目前不影响结果；
# 加中文词汇表时也不会——它的起始字符与这三种都不同。
VOCABULARIES: tuple[Vocabulary, ...] = (_Decimal(), _Paren(), _Letter())


def parse_label(line: str) -> Numbering | None:
    """认出行首编号；认不出返回 None。不做任何"是不是标题"的判断。"""
    for vocabulary in VOCABULARIES:
        found = vocabulary.match(line)
        if found is not None:
            return found
    return None
