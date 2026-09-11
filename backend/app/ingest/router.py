import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.clauses.schemas import ClauseTreeOut
from app.db import get_session
from app.errors import AppError, Conflict, NotFound
from app.iam.audit import record
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.ingest.coverage import document_coverage, uncovered_clauses
from app.ingest.models import DocStatus, DocType, Document
from app.ingest.schemas import (
    DocumentCoverageOut,
    DocumentMetaIn,
    DocumentOut,
    PlainTextIn,
    UncoveredClauseOut,
)
from app.ingest.service import find_by_hash
from app.ingest.storage import ALLOWED_EXTENSIONS, sha256_of
from app.worker import enqueue

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: DocType = Form(...),
    supersedes_id: int | None = Form(None),
    actor: User = Depends(require(Permission.DOCUMENT_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> Document:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(
            f"不支持的文件类型 {extension or '(无扩展名)'}。"
            "Excel 控制矩阵导入属于 M4，目前只支持 .pdf 与 .docx。"
        )

    content = await file.read()
    digest = sha256_of(content)
    existing = await find_by_hash(session, digest)
    if existing is not None:
        raise Conflict(f"该文件已存在（文档 #{existing.id}：{existing.title}）")

    with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir="/tmp") as handle:
        handle.write(content)
        staged = handle.name

    document = Document(
        title=title,
        doc_type=doc_type,
        status=DocStatus.UPLOADED,
        original_filename=file.filename or f"upload{extension}",
        file_hash=digest,
        file_path=staged,
        uploaded_by=actor.id,
        supersedes_id=supersedes_id,
    )
    session.add(document)
    await session.flush()

    await record(
        session,
        user=actor,
        action="document.upload",
        entity_type="Document",
        entity_id=document.id,
        after={"title": title, "doc_type": doc_type.value, "filename": document.original_filename},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    await enqueue("parse_document", document.id)
    return document


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    status_filter: DocStatus | None = Query(default=None, alias="status"),
    doc_type: DocType | None = None,
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> list[Document]:
    statement = select(Document).order_by(Document.id.desc())
    if status_filter:
        statement = statement.where(Document.status == status_filter)
    if doc_type:
        statement = statement.where(Document.doc_type == doc_type)
    return list(await session.scalars(statement))


@router.get("/coverage", response_model=list[DocumentCoverageOut])
async def coverage(
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentCoverageOut]:
    """你自己的制度里，有多少要求还没变成控制点。

    与框架覆盖度方向相反：那个问「外部要求有没有被满足」，这个问「我们写下的
    要求有没有被系统看见」。两种盲区都是静默的——不扫就没有任何地方会提示。
    """
    return [
        DocumentCoverageOut(**{**row.__dict__, "never_extracted": row.never_extracted})
        for row in await document_coverage(session)
    ]


@router.get("/{document_id}/uncovered", response_model=list[UncoveredClauseOut])
async def uncovered(
    document_id: int,
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> list[UncoveredClauseOut]:
    return [UncoveredClauseOut(**row.__dict__)
            for row in await uncovered_clauses(session, document_id)]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: int,
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")
    return document


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document_meta(
    document_id: int,
    body: DocumentMetaIn,
    actor: User = Depends(require(Permission.DOCUMENT_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(document, field, value)
    await session.flush()
    await record(
        session,
        user=actor,
        action="document.meta_update",
        entity_type="Document",
        entity_id=document.id,
        after={"fields": sorted(changes)},
    )
    await session.commit()
    return document


@router.get("/{document_id}/clauses", response_model=list[ClauseTreeOut])
async def get_clauses(
    document_id: int,
    _: User = Depends(require(Permission.READ)),
    session: AsyncSession = Depends(get_session),
) -> list[ClauseTreeOut]:
    rows = list(
        await session.scalars(
            select(Clause)
            .where(Clause.document_id == document_id)
            .order_by(Clause.order_index)
        )
    )
    nodes = {row.id: ClauseTreeOut.model_validate(row) for row in rows}
    roots: list[ClauseTreeOut] = []
    for row in rows:
        node = nodes[row.id]
        parent = nodes.get(row.parent_id) if row.parent_id else None
        (parent.children if parent else roots).append(node)
    return roots


@router.post("/{document_id}/plain-text", response_model=DocumentOut)
async def replace_with_plain_text(
    document_id: int,
    payload: PlainTextIn,
    request: Request,
    actor: User = Depends(require(Permission.DOCUMENT_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> Document:
    """Recover a failed document by splitting manually pasted numbered text."""
    from app.parsing.flatten import persist
    from app.parsing.numbering import assemble_tree, extract_headings

    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")

    lines = payload.text.splitlines()
    headings, warnings = extract_headings(lines)
    count = await persist(session, assemble_tree(headings, lines), document_id=document.id)

    document.status = DocStatus.ACTIVE
    document.parse_error = None
    document.parse_warnings = "\n".join([*warnings, f"由人工粘贴的纯文本生成 {count} 条条款"])
    await session.flush()

    await record(
        session,
        user=actor,
        action="document.plain_text_fallback",
        entity_type="Document",
        entity_id=document.id,
        after={"clauses": count},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return document


@router.post("/{document_id}/reparse", response_model=DocumentOut)
async def reparse(
    document_id: int,
    request: Request,
    actor: User = Depends(require(Permission.DOCUMENT_WRITE)),
    session: AsyncSession = Depends(get_session),
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")
    await record(
        session,
        user=actor,
        action="document.reparse",
        entity_type="Document",
        entity_id=document.id,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    await enqueue("parse_document", document.id)
    return document
