from sqlalchemy import ForeignKey, Index, Integer, String, Text
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
