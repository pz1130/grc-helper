from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin


class Clause(Base, TimestampMixin):
    """The citation atom for every parsed document."""

    __tablename__ = "clauses"
    __table_args__ = (Index("ix_clauses_document_order", "document_id", "order_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"), nullable=True
    )

    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heading: Mapped[str] = mapped_column(String(1000), nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    citation_label: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    page_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="section", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    document: Mapped["Document"] = relationship(back_populates="clauses")  # noqa: F821


# pgvector 的列必须声明维度。固定 1536：OpenAI text-embedding-3-* 可用。
# 换用其他维度的模型 = 一次新迁移 + 一次全量重建。
EMBEDDING_DIM = 1536


class ClauseChunk(Base, TimestampMixin):
    """检索单元。

    引用锚点仍然是 Clause——chunk 只是为了让长条款能被切开检索。
    命中之后一律回指 clause，对外展示 clause.citation_label。
    """

    __tablename__ = "clause_chunks"
    __table_args__ = (
        UniqueConstraint("clause_id", "chunk_index", name="uq_chunk_per_clause"),
        Index("ix_chunk_document", "document_id"),
        Index("ix_chunk_embedding_model", "embedding_model"),
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clause_id: Mapped[int] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 刻意冗余：按文档过滤检索是高频操作，省掉每次 JOIN。随 clause 级联删除，不会漂移。
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # 先落库再异步向量化，所以可为空。
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    # 生成列：全文索引不需要应用层维护。语料为纯英文，用 english 配置。
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), nullable=True
    )
