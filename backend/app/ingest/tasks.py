"""Asynchronous document parsing tasks."""

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_factory
from app.ingest.models import DocStatus, DocType, Document
from app.ingest.storage import save
from app.parsing.contract import ParseError
from app.parsing.flatten import persist
from app.parsing.registry import get_parser
from app.parsing.validate import check_completeness


async def run_parse(session: AsyncSession, document: Document) -> dict[str, Any]:
    """Run parsing independently from ARQ so it can be tested directly."""
    document.status = DocStatus.PARSING
    document.parse_error = None
    await session.flush()

    try:
        path = Path(document.file_path)
        if path.parent == Path("/tmp"):
            stored = save(path.read_bytes(), document.original_filename)
            document.file_path = stored.path
            path.unlink(missing_ok=True)
            await session.flush()
            path = Path(document.file_path)
        parsed = get_parser(path).parse(path)
    except ParseError as exc:
        document.status = DocStatus.PARSE_FAILED
        document.parse_error = exc.reason
        await session.flush()
        raise
    except Exception as exc:  # noqa: BLE001
        document.status = DocStatus.PARSE_FAILED
        document.parse_error = f"解析时发生未预期的错误：{type(exc).__name__}: {exc}"
        await session.flush()
        raise

    warnings = [*parsed.warnings, *check_completeness(parsed)]
    count = await persist(session, parsed.clauses, document_id=document.id)

    meta = parsed.meta
    document.version = meta.version or document.version
    document.owner = meta.owner or document.owner
    document.approver = meta.approver or document.approver
    document.approved_date = meta.approved_date or document.approved_date
    document.effective_date = meta.effective_date or document.effective_date
    if meta.doc_type:
        document.doc_type = DocType(meta.doc_type)

    document.ocr_quality_flag = parsed.ocr_used
    document.parse_warnings = "\n".join(warnings) if warnings else None
    document.status = DocStatus.ACTIVE
    await session.flush()

    return {"clauses": count, "warnings": warnings}


async def parse_document(ctx: dict[str, Any], document_id: int) -> dict[str, Any]:
    """ARQ task entrypoint."""
    # try/finally 必须在 async with **内部**：session 一 close，document 就变成
    # detached 对象，对它的所有赋值（status、file_path、封面元数据）在 flush 时
    # 会被静默丢弃——而 persist() 新 add 的 Clause 照常落库，所以看起来"解析成功了"，
    # 实际文档状态永远停在 uploaded、file_path 还指向已被删掉的 /tmp 路径。
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return {"clauses": 0, "warnings": [f"文档 {document_id} 不存在"]}
        try:
            result = await run_parse(session, document)
        finally:
            await session.commit()

    # 解析成功后自动接上分块与向量化，避免用户手动触发第二个任务。
    from app.worker import enqueue

    await enqueue("index_document", document_id)
    return result
