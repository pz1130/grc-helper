"""解析层的对外契约。

parsing 不碰数据库：只接受路径、返回 ParsedDocument。
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol


class ParseError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class ClauseNode:
    heading: str
    text: str
    level: int
    number: str | None = None
    page_ref: int | None = None
    kind: str = "section"
    children: list["ClauseNode"] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentMeta:
    title: str | None
    version: str | None
    owner: str | None
    approver: str | None
    approved_date: date | None
    effective_date: date | None
    doc_type: str | None


@dataclass(frozen=True)
class ParsedDocument:
    meta: DocumentMeta
    clauses: list[ClauseNode]
    warnings: list[str] = field(default_factory=list)
    ocr_used: bool = False


class Parser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...
