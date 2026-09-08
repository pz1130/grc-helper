from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.models import DocStatus, DocType, Document
from app.ingest.storage import StoredFile


async def find_by_hash(session: AsyncSession, sha256: str) -> Document | None:
    return await session.scalar(select(Document).where(Document.file_hash == sha256))


async def register(
    session: AsyncSession,
    *,
    stored: StoredFile,
    original_filename: str,
    title: str,
    doc_type: DocType,
    uploaded_by: int | None,
    supersedes_id: int | None = None,
) -> Document:
    document = Document(
        title=title,
        doc_type=doc_type,
        status=DocStatus.UPLOADED,
        original_filename=original_filename,
        file_hash=stored.sha256,
        file_path=stored.path,
        uploaded_by=uploaded_by,
        supersedes_id=supersedes_id,
    )
    session.add(document)
    await session.flush()
    return document


async def mark_superseded(session: AsyncSession, doc: Document) -> None:
    doc.status = DocStatus.SUPERSEDED
    await session.flush()
